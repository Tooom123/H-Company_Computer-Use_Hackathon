"""Loopback-only voice pilot; engine contracts remain owned by Matteo.

The launcher supplies a bearer token, private storage and optional STT/export/store
adapters. This module never discovers credentials or starts a desktop intervention
without the existing explicit /approve step. Bind the returned app to 127.0.0.1.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from hcs_agent.contract import FeedbackCommand, InterventionRequest
from hcs_agent.procedures import ProcedureRegistry
from hcs_agent.server import create_app as engine_app, _snapshot

from .catalog import load_catalog
from .environments import get_environment

MAX_AUDIO_BYTES = 12 * 1024 * 1024
MAX_AUDIO_SECONDS = 90
SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$')
REPO = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def audio_duration(path: Path, mime: str) -> float:
    if mime in {'audio/wav', 'audio/x-wav', 'audio/wave'}:
        try:
            with wave.open(str(path), 'rb') as wav:
                frames, channels, width, rate = wav.getnframes(), wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
                if channels not in (1, 2) or width != 2 or not 8000 <= rate <= 96000:
                    raise ValueError('Expected 16-bit PCM WAV, one or two channels')
                if len(wav.readframes(frames)) != frames * channels * width:
                    raise ValueError('Truncated WAV')
                return frames / rate
        except (wave.Error, EOFError, ValueError):
            raise HTTPException(422, 'Audio WAV invalide : utilisez PCM 16 bits, mono ou stéréo.') from None
    executable = shutil.which('ffprobe')
    decoder = shutil.which('ffmpeg')
    if executable is None or decoder is None:
        raise HTTPException(415, 'WebM nécessite ffmpeg et ffprobe ; envoyez un WAV PCM 16 bits.')
    try:
        result = subprocess.run([executable, '-v', 'error', '-show_entries',
                                 'format=duration:stream=codec_type,duration', '-of', 'json', str(path)],
                                capture_output=True, timeout=10, check=True)
        info = json.loads(result.stdout)
        streams = info.get('streams', [])
        if not streams or any(s.get('codec_type') != 'audio' for s in streams):
            raise ValueError('Expected audio only')
        # MediaRecorder WebM often omits duration. Decode a bounded prefix instead
        # of trusting a header: 90.1 seconds is enough to reject an overlong file.
        decoded = subprocess.run([decoder, '-nostdin', '-v', 'error', '-i', str(path),
                                  '-map', '0:a:0', '-vn', '-t', '90.1', '-ac', '1',
                                  '-ar', '16000', '-f', 's16le', 'pipe:1'],
                                 capture_output=True, timeout=20, check=True)
        return len(decoded.stdout) / (16000 * 2)
    except (ValueError, KeyError, subprocess.SubprocessError):
        raise HTTPException(422, 'Durée WebM non vérifiable ; envoyez un WAV PCM 16 bits.') from None


class EpisodeBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario_id: str
    goal: str = Field(min_length=1, max_length=20000)
    request_audio_id: str | None = None
    run_reference: str | None = None
    workflow_id: str | None = None


class PilotFeedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_success_user: Literal['success', 'partial', 'failed', 'unknown']
    useful: Literal['yes', 'no', 'unknown']
    comment: str = Field(default='', max_length=20000)
    audio_id: str | None = None
    allow_training: bool = False


class LocalAuth:
    """Protect HTTP and WebSocket, including inherited engine routes."""
    def __init__(self, app, token: str):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        supplied = headers.get(b'authorization', b'').decode('latin-1')
        valid = hmac.compare_digest(supplied, 'Bearer ' + self.token)
        # Electron's privileged IPC proxy sends no Origin. Web pages cannot call it.
        valid = valid and b'origin' not in headers
        if not valid:
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 4401})
            else:
                await JSONResponse({'detail': 'Unauthorized local pilot request'}, status_code=401)(scope, receive, send)
            return
        path, method = scope.get('path', ''), scope.get('method', '')
        if method == 'POST' and (path == '/interventions' or
                                 re.fullmatch(r'/interventions/[^/]+/feedback', path)):
            await JSONResponse({'detail': 'Use the pilot episode/feedback routes'}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_app(*, private_root: Path, token: str, backend=None, transcriber=None,
               exporter=None, store=None, model: str = 'holo4-35b-a3b',
               scenarios_path: Path | None = None, procedures_dir: Path | None = None,
               environment: str = 'minimal', engine_revision: str | None = None,
               support_revision: str | None = None):
    """Wrap Matteo's app. Callbacks: STT(path,mime), export(report_path,archive_dir).

    STT returns a string or {transcript, provider}; optional .provider/.ready/.message
    attributes describe availability. Export returns a JSON-serializable manifest.
    Tom Store is optional; add_case(report) upserts and add_event(event) persists.
    """
    if len(token) < 16:
        raise ValueError('Use a randomly generated local bearer token of at least 16 characters')
    demo = get_environment(environment)
    os.umask(0o077)
    root = Path(private_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    identity_path = root / 'environment.json'
    if identity_path.exists():
        previous_demo = read_json(identity_path)
        if any(previous_demo.get(key) != demo.get(key) for key in ('id', 'company', 'fixture_version')):
            raise ValueError('This private directory belongs to another demo environment.')
    elif environment != 'minimal' and any((root / 'episodes').glob('*/episode.json')):
        raise ValueError('Existing untagged episodes belong to the initial demo; use a new private directory.')
    atomic_json(identity_path, demo)
    for folder in ('audio', 'episodes', 'archives'):
        (root / folder).mkdir(exist_ok=True, mode=0o700)
    if environment == 'rich':
        from .rich_catalog import load_rich_catalog
        cards = load_rich_catalog()
    else:
        cards = load_catalog(scenarios_path or REPO / 'docs/scenarios/odoo-scenarios.md')
    catalog = {card['id']: card for card in cards}
    app = engine_app(backend=backend, runs_dir=root / 'episodes')
    hub = app.state.hub
    hub.registry = ProcedureRegistry(procedures_dir or REPO / 'docs/scenarios')
    for card in cards:
        hub.registry.get(card['procedure_id'])  # fail setup, not halfway through a recording
    app.add_middleware(LocalAuth, token=token)
    lock = threading.RLock()
    exports = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pilot-export')
    original_lifespan = app.router.lifespan_context
    exporter_started: set[str] = set()
    closing = threading.Event()
    app.state.pilot_root = root

    def episode_dir(sid: str) -> Path:
        if not SAFE_ID.fullmatch(sid):
            raise HTTPException(404, 'Unknown episode')
        result = root / 'episodes' / sid
        if not (result / 'episode.json').is_file():
            raise HTTPException(404, 'Unknown episode')
        return result

    def metadata(sid: str) -> dict:
        return read_json(episode_dir(sid) / 'episode.json')

    def update_meta(sid: str, **changes):
        data = metadata(sid)
        data.update(changes)
        atomic_json(episode_dir(sid) / 'episode.json', data)

    def store_report(report: dict, sid: str):
        if store is not None:
            try:
                store.add_case(report)
                update_meta(sid, store_status='saved')
            except Exception as exc:
                update_meta(sid, store_status='error', store_error=type(exc).__name__)

    def export_finished(sid: str):
        directory = episode_dir(sid)
        try:
            # The engine's feedback writer is non-atomic. Give the exporter a frozen
            # input, then refresh the archived report/labels under our lock below.
            with lock:
                export_input = directory / 'export-report.json'
                atomic_json(export_input, read_json(directory / 'report.json'))
            result = exporter(export_input, root / 'archives' / sid)
            with lock:
                # Copy the latest labels and report after export so concurrent feedback
                # cannot leave the exported copy older than the local episode.
                archive = root / 'archives' / sid
                if archive.is_dir():
                    for filename in ('report.json', 'labels.json', 'request.json', 'procedure.json', 'agent-review.json', 'quarantine.json'):
                        source = directory / filename
                        if source.exists():
                            target = archive / filename
                            if filename.endswith('.json'):
                                atomic_json(target, read_json(source))
                            else:
                                shutil.copyfile(source, target)
                                os.chmod(target, 0o600)
                complete = isinstance(result, dict) and (result.get('archive_complete') is True or result.get('complete') is True)
                update_meta(sid, export_status='complete' if complete else 'partial',
                            export_result=result, export_finished_at=now())
        except Exception as exc:
            with lock:
                update_meta(sid, export_status='failed', export_error=type(exc).__name__, export_finished_at=now())

    def schedule_export(sid: str, report: dict):
        if sid in exporter_started:
            return
        exporter_started.add(sid)
        if report.get('simulated') is not False:
            update_meta(sid, export_status='skipped_simulated')
        elif not report.get('h_session_ids'):
            update_meta(sid, export_status='skipped_no_h_session')
        elif exporter is None:
            update_meta(sid, export_status='not_configured')
        elif closing.is_set():
            update_meta(sid, export_status='interrupted')
        else:
            update_meta(sid, export_status='exporting')
            try:
                exports.submit(export_finished, sid)
            except RuntimeError:
                # A stopped intervention may emit its final report during shutdown.
                update_meta(sid, export_status='interrupted')

    original_sink = hub._sink

    def sink(event):
        data = event.model_dump(mode='json')
        sid = event.session_id
        with lock:
            directory = episode_dir(sid)
            fd = os.open(directory / 'events.jsonl', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as stream:
                stream.write(json.dumps(data, ensure_ascii=False) + '\n')
            update_meta(sid, state=event.state.value, last_event_at=now())
            if store is not None:
                try:
                    store.add_event(data)
                except Exception as exc:
                    update_meta(sid, store_status='error', store_error=type(exc).__name__)
            if event.type == 'finished':
                report = data['data']['report']
                # Keep a separate atomic final artifact even though the inherited
                # engine also writes report.json before emitting finished.
                atomic_json(directory / 'report.json', report)
                it = hub.interventions.get(sid)
                if it is not None:
                    atomic_json(directory / 'snapshot.json', _snapshot(it))
                update_meta(sid, finished_at=now())
                store_report(report, sid)
                schedule_export(sid, report)
        original_sink(event)

    hub._sink = sink

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            try:
                yield
            finally:
                closing.set()
                # Close the local action gate before waiting for report persistence.
                for it in list(hub.interventions.values()):
                    if not it.state.terminal:
                        from hcs_agent.contract import StopCommand
                        it.stop(StopCommand(reason='pilot server shutdown'))
                    await run_in_threadpool(it.wait, 2)
                hub.loop = None
                exports.shutdown(wait=False)

    app.router.lifespan_context = lifespan

    def busy() -> bool:
        return any(not it.state.terminal or it.report is None for it in hub.interventions.values())

    def audio_meta(audio_id: str | None, purpose: str) -> dict | None:
        if audio_id is None:
            return None
        if not SAFE_ID.fullmatch(audio_id):
            raise HTTPException(422, 'Unknown audio')
        path = root / 'audio' / (audio_id + '.json')
        if not path.is_file():
            raise HTTPException(422, 'Unknown audio')
        data = read_json(path)
        if data.get('purpose') != purpose or data.get('status') != 'transcribed':
            raise HTTPException(422, 'Audio has the wrong purpose or was not transcribed')
        return data

    def snapshot(sid: str) -> dict:
        directory = episode_dir(sid)
        meta = metadata(sid)
        it = hub.interventions.get(sid)
        if it is not None:
            result = _snapshot(it)
            report = it.report.model_dump(mode='json') if it.report is not None and meta.get('finished_at') else None
        else:
            saved = directory / 'snapshot.json'
            result = read_json(saved) if saved.exists() else {'session_id': sid, 'state': meta.get('state', 'failed'),
                        'simulated': meta['simulated'], 'request': read_json(directory / 'request.json')['intervention']}
            report = read_json(directory / 'report.json') if (directory / 'report.json').is_file() else None
            result['restored_read_only'] = True
            if report is None:
                result.update(state='failed', error='Serveur redémarré avant le rapport ; ne pas reprendre automatiquement.')
            else:
                # The process can exit between report.json and snapshot.json writes.
                terminal = {'resolved', 'escalated', 'stopped', 'failed', 'preflight_failed'}
                result['state'] = meta.get('state') if meta.get('state') in terminal else {
                    'resolved': 'resolved', 'escalated': 'escalated', 'abandoned': 'stopped',
                }.get(report.get('status'), 'failed')
            if meta.get('export_status') == 'exporting':
                meta['export_status'] = 'interrupted'
        result['report'] = report
        result['report_ready'] = report is not None
        result['pilot'] = meta
        if (directory / 'labels.json').exists():
            result['pilot']['feedback'] = read_json(directory / 'labels.json')
        if (directory / 'agent-review.json').exists():
            result['pilot']['agent_review'] = read_json(directory / 'agent-review.json')
        if (directory / 'quarantine.json').exists():
            quarantine = read_json(directory / 'quarantine.json')
            result['pilot']['quarantine'] = {'status': quarantine.get('status', 'quarantined'),
                'reason': 'Capture hors périmètre à revoir ; trace exclue de l’entraînement.'}
        return result

    @app.get('/pilot/status')
    def status():
        provider = getattr(transcriber, 'provider', 'configured' if transcriber else 'none')
        ready = transcriber is not None and bool(getattr(transcriber, 'ready', True))
        return {'model': model, 'simulated': bool(hub.backend.simulated), 'busy': busy(),
                'environment': demo, 'engine_revision': engine_revision, 'support_revision': support_revision,
                'transcription': {'provider': provider, 'ready': ready,
                                  'message': getattr(transcriber, 'message', 'Prêt' if ready else 'Transcription non configurée')}}

    @app.get('/pilot/scenarios')
    def scenarios():
        return cards

    @app.post('/pilot/audio')
    async def upload_audio(request: Request, purpose: Literal['request', 'feedback']):
        if transcriber is None or not getattr(transcriber, 'ready', True):
            raise HTTPException(503, 'Transcription non configurée ; la saisie texte reste disponible.')
        if busy():
            raise HTTPException(409, 'Attendez la fin du passage avant d’enregistrer.')
        mime = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
        if mime not in {'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/webm'}:
            raise HTTPException(415, 'Envoyez un WAV PCM 16 bits ou un WebM audio.')
        audio_id = 'audio_' + uuid.uuid4().hex
        path = root / 'audio' / (audio_id + ('.webm' if mime == 'audio/webm' else '.wav'))
        size = 0
        try:
            with path.open('xb') as stream:
                os.chmod(path, 0o600)
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_AUDIO_BYTES:
                        raise HTTPException(413, 'Enregistrement limité à 12 Mio.')
                    stream.write(chunk)
            duration = await run_in_threadpool(audio_duration, path, mime)
            if not math.isfinite(duration) or not 0.1 <= duration <= MAX_AUDIO_SECONDS:
                raise HTTPException(422, 'Enregistrement limité à 90 secondes, au moins 0,1 seconde.')
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        meta = {'audio_id': audio_id, 'purpose': purpose, 'created_at': now(), 'content_type': mime,
                'file': path.name, 'size': size, 'duration_s': duration,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'status': 'transcribing'}
        atomic_json(root / 'audio' / (audio_id + '.json'), meta)
        try:
            value = await run_in_threadpool(transcriber, path, mime)
            transcript = value.get('transcript') if isinstance(value, dict) else value
            provider = value.get('provider', 'configured') if isinstance(value, dict) else getattr(transcriber, 'provider', 'configured')
            if not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 20000:
                raise ValueError('Empty or oversized transcript')
        except Exception as exc:
            meta.update(status='failed', error=type(exc).__name__)
            atomic_json(root / 'audio' / (audio_id + '.json'), meta)
            raise HTTPException(502, 'Transcription échouée ; audio privé conservé, saisie texte disponible.') from None
        meta.update(status='transcribed', transcript=transcript, provider=str(provider))
        atomic_json(root / 'audio' / (audio_id + '.json'), meta)
        return {'audio_id': audio_id, 'transcript': transcript, 'provider': str(provider)}

    @app.post('/pilot/episodes', status_code=201)
    def create_episode(body: EpisodeBody):
        with lock:
            if busy():
                raise HTTPException(409, 'Un passage est déjà actif sur ce Mac.')
            card = catalog.get(body.scenario_id)
            if card is None or not body.goal.strip():
                raise HTTPException(422, 'Scénario inconnu ou demande vide.')
            if card['requires_reference'] and (not body.run_reference or not SAFE_ID.fullmatch(body.run_reference)):
                raise HTTPException(422, 'Une référence de passage valide est obligatoire pour les scénarios 05–10.')
            if body.workflow_id is not None and not SAFE_ID.fullmatch(body.workflow_id):
                raise HTTPException(422, 'Identifiant de workflow invalide.')
            workflow = body.workflow_id or (('odoo-purchase-' + body.run_reference) if card['requires_reference'] else None)
            if card.get('depends_on'):
                previous_verified = False
                for previous_path in (root / 'episodes').glob('*/episode.json'):
                    previous = read_json(previous_path)
                    if (previous.get('scenario_id') == card['depends_on'] and
                            previous.get('environment', {}).get('id', 'odoo-minimal-v1') == demo['id'] and
                            previous.get('workflow_id') == workflow and previous.get('run_reference') == body.run_reference):
                        report_path = previous_path.parent / 'report.json'
                        if report_path.is_file() and previous.get('finished_at'):
                            previous_report = read_json(report_path)
                            previous_verified = previous_verified or (
                                previous_report.get('verification', {}).get('satisfied') is True and
                                previous_report.get('simulated') is bool(hub.backend.simulated))
                if not previous_verified:
                    raise HTTPException(409, f"Le scénario {card['depends_on']} doit être vérifié dans le même cycle et avec la même référence.")
            audio = audio_meta(body.request_audio_id, 'request')
            params = {'run_reference': body.run_reference} if card['requires_reference'] else {}
            req = InterventionRequest(software='odoo', software_version='20.0', role='commerçant, première semaine sur Odoo',
                    goal=body.goal, procedure_id=card['procedure_id'], parameters=params, mode='act')
            directory = root / 'episodes' / req.session_id
            directory.mkdir(mode=0o700)
            workflow = workflow or req.session_id
            initial = {'session_id': req.session_id, 'scenario_id': card['id'], 'title': card['title'],
                       'procedure_id': card['procedure_id'], 'workflow_id': workflow, 'run_reference': body.run_reference,
                       'created_at': now(), 'state': 'created', 'simulated': bool(hub.backend.simulated),
                       'model': model, 'mode': 'act', 'image_policy': 'full_screen',
                       'environment': demo, 'engine_revision': engine_revision, 'support_revision': support_revision,
                       'desktop_adapter': getattr(hub.backend, 'adapter_revision', None),
                       'request_audio_id': body.request_audio_id, 'export_status': 'pending',
                       'store_status': 'pending' if store is not None else 'not_configured'}
            atomic_json(directory / 'episode.json', initial)
            atomic_json(directory / 'request.json', {'intervention': req.model_dump(mode='json'),
                        'goal_raw': body.goal, 'audio': audio, 'scenario': card, 'workflow_id': workflow,
                        'environment': demo, 'engine_revision': engine_revision, 'support_revision': support_revision})
            procedure = hub.registry.get(card['procedure_id'])
            atomic_json(directory / 'procedure.json', procedure.model_dump(mode='json'))
            it = hub.create(req)
            atomic_json(directory / 'snapshot.json', _snapshot(it))
            return snapshot(req.session_id)

    @app.get('/pilot/episodes/{sid}')
    def get_episode(sid: str):
        with lock:
            return snapshot(sid)

    @app.post('/pilot/episodes/{sid}/feedback')
    def feedback(sid: str, body: PilotFeedback):
        with lock:
            directory = episode_dir(sid)
            it = hub.interventions.get(sid)
            if it is None:
                raise HTTPException(409, 'Épisode restauré en lecture seule ; conserver le retour hors de ce serveur.')
            if not it.state.terminal or it.report is None or not metadata(sid).get('finished_at'):
                raise HTTPException(409, 'Le feedback est enregistré après la fin du passage.')
            audio = audio_meta(body.audio_id, 'feedback')
            original_verification = it.report.verification.model_dump(mode='json')
            useful = {'yes': True, 'no': False, 'unknown': None}[body.useful]
            it.add_feedback(FeedbackCommand(useful=useful, comment=body.comment, allow_screenshots_to_support=False))
            report = it.report.model_dump(mode='json')
            assert report['verification'] == original_verification
            atomic_json(directory / 'report.json', report)
            labels = {'task_success_user': body.task_success_user, 'useful': body.useful, 'comment': body.comment,
                      'audio_id': body.audio_id, 'raw_transcript': audio.get('transcript') if audio else None,
                      'audio': audio, 'allow_training': body.allow_training, 'include_for_training': False,
                      'reviewed': False, 'user_confirmed': True, 'confirmed_at': now(),
                      'simulated': bool(hub.backend.simulated),
                      'objective_success': original_verification.get('satisfied'),
                      'objective_source': 'engine_verification', 'objective_evidence': ['report.json']}
            atomic_json(directory / 'labels.json', labels)
            update_meta(sid, feedback=labels)
            store_report(report, sid)
            archive = root / 'archives' / sid
            if archive.is_dir():
                atomic_json(archive / 'report.json', report)
                atomic_json(archive / 'labels.json', labels)
            return snapshot(sid)

    return app
