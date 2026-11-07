"""Read-only live supervision of explicitly configured private episode stores.

Cloud frames must have a writer-created manifest and an explicit display grant.
Historical before/after images are never discovered or exposed automatically.
No H key, signed resource URL, credential or filesystem path reaches the client.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path, PurePosixPath
import re
import secrets
from typing import Iterable
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import HTMLResponse, JSONResponse, Response

SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$')
HASH = re.compile(r'^[a-fA-F0-9]{64}$')
TERMINAL = {'resolved', 'escalated', 'completed', 'failed', 'failure', 'stopped',
            'preflight_failed', 'cancelled', 'interrupted', 'timed_out'}
VISIBLE_PHASES = {'working', 'running', 'executing', 'verifying', 'coaching', 'completed'}
HIDDEN_PHASES = {'auth', 'login', 'authentication', 'credentials', 'credential', 'vault',
                 'awaiting_auth', 'awaiting_2fa', 'two_factor', 'observation_hidden', 'quarantine', 'quarantined'}
MAX_JSON = 4 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_EPISODES = 100
HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache',
           'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin',
           'Cross-Origin-Resource-Policy': 'same-origin'}
SECRET_PATTERNS = [
    re.compile(r'\bhk-[A-Za-z0-9_-]{20,}\b'),
    re.compile(r'\bsk_gladia_[A-Za-z0-9_-]{16,}\b'),
    re.compile(r'AGE-SECRET-KEY-1[A-Z0-9]+'),
    re.compile(r'-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|$)', re.S),
]


@dataclass(frozen=True)
class ControlTowerSource:
    id: str
    label: str
    root: Path
    software: str = ''


def _text(value, limit=1200):
    if not isinstance(value, (str, int, float, bool)):
        return ''
    result = str(value)
    for pattern in SECRET_PATTERNS:
        result = pattern.sub('[secret masqué]', result)
    def redact_url(match):
        try:
            url = urlsplit(match.group(0))
            sensitive = {'token', 'access_token', 'api_key', 'signature', 'sig', 'secret'}
            if url.username or url.password or any(k.lower() in sensitive or k.lower().startswith('x-amz-')
                                                    for k, _ in parse_qsl(url.query)):
                return '[lien privé masqué]'
        except ValueError:
            return '[lien invalide masqué]'
        return match.group(0)
    result = re.sub(r'https?://[^\s<>"\']+', redact_url, result)
    result = ''.join(c for c in result if c in '\n\t' or ord(c) >= 32)
    return result[:limit]


def _json(directory: Path, name: str):
    path = directory / name
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        if path.stat().st_size > MAX_JSON:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, ValueError):
        return {}


def _dict(value):
    return value if isinstance(value, dict) else {}


def _quarantined(directory: Path, meta: dict):
    marker = directory / 'quarantine.json'
    return (marker.exists() or marker.is_symlink() or meta.get('quarantined') is True
            or meta.get('scope_violation') is True
            or str(meta.get('phase', '')).lower() in {'quarantine', 'quarantined'})


def _frames(directory: Path, meta: dict):
    if (not meta or _quarantined(directory, meta)
            or meta.get('display_blocked') is True or meta.get('authentication_required') is True
            or str(meta.get('phase', '')).lower() in HIDDEN_PHASES):
        return []
    rows = _json(directory, 'frames.json').get('frames', [])
    if not isinstance(rows, list):
        return []
    result = []
    for frame in rows[-1000:]:
        if not isinstance(frame, dict) or frame.get('display_allowed') is not True:
            continue
        if str(frame.get('phase', '')).lower() not in VISIBLE_PHASES:
            continue
        frame_id = str(frame.get('id', ''))
        path = frame.get('path', frame.get('filename'))
        digest = frame.get('sha256')
        if (not SAFE_ID.fullmatch(frame_id) or not isinstance(path, str)
                or not isinstance(digest, str) or not HASH.fullmatch(digest)):
            continue
        relative = PurePosixPath(path)
        if (len(relative.parts) != 2 or relative.parts[0] != 'frames'
                or relative.name not in {frame_id + suffix for suffix in ('.png', '.jpg', '.jpeg', '.webp')}):
            continue
        folder, file = directory / 'frames', directory / path
        if folder.is_symlink() or file.is_symlink() or not file.is_file():
            continue
        result.append({'id': frame_id, 'path': path, 'sha256': digest.lower(),
                       'timestamp': _text(frame.get('timestamp', frame.get('captured_at')), 80),
                       'index': frame.get('index') if type(frame.get('index')) is int else len(result)})
    return result


def _events(directory: Path, count=20):
    """Read a bounded tail, excluding reasoning and raw tool arguments/resources."""
    file = directory / 'events.jsonl'
    if file.is_symlink() or not file.is_file():
        return []
    try:
        with file.open('rb') as stream:
            size = file.stat().st_size
            stream.seek(max(0, size - 65536))
            if size > 65536:
                stream.readline()  # discard partial first line
            lines = stream.read(65536).splitlines()
    except OSError:
        return []
    result = []
    allowed = {'state', 'status', 'state_changed', 'phase', 'step', 'action', 'action_event',
               'observation', 'observation_event', 'message', 'message_event', 'answer',
               'answer_event', 'error', 'tool_error', 'blocked', 'guidance', 'instruction',
               'verification', 'attempt_started', 'attempt_finished', 'finished', 'archive',
               'created', 'session_created', 'session_started', 'session_finished', 'frame'}
    for line in lines:
        if len(line) > 16384:
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get('type', event.get('kind'))
        if kind == 'provider_event':
            # Cloud runtime publishes sanitized messages separately from raw
            # provider payloads. Unknown/analysis kinds remain hidden.
            kind = event.get('provider_kind')
        if not isinstance(kind, str) or kind not in allowed or str(event.get('phase', '')).lower() in HIDDEN_PHASES:
            continue
        data = _dict(event.get('data'))
        step = _dict(data.get('step'))
        if kind == 'step' and step.get('kind') in {'thought', 'reasoning', 'analysis'}:
            continue
        # The writer's public message is accepted; never serialize data/args or
        # H's raw reasoning payload. Action tools are names only, not arguments.
        message = event.get('message', event.get('summary', ''))
        if kind in {'action', 'action_event'} and not message:
            tools = event.get('tool_names', [])
            message = 'Action navigateur' + (': ' + ', '.join(_text(t, 80) for t in tools[:5]) if isinstance(tools, list) and tools else '')
        if kind in {'observation', 'observation_event', 'frame'}:
            message = 'Nouvel écran reçu'
        result.append({'type': kind, 'timestamp': _text(event.get('timestamp', event.get('ts')), 80),
                       'message': _text(message), 'state': _text(event.get('state'), 40)})
    return result[-count:]


def _verdict(value):
    return value if isinstance(value, str) and value in {'success', 'partial', 'failure', 'failed', 'unknown'} else None


def _record(source: ControlTowerSource, directory: Path, *, detail=False):
    meta = _json(directory, 'episode.json')
    if not meta:
        return None
    row = {'id': directory.name, 'source_id': source.id, 'source_label': source.label,
           'software': source.software, 'state': _text(meta.get('state', meta.get('status', 'unknown')), 50),
           'phase': _text(meta.get('phase', ''), 50), 'created_at': _text(meta.get('created_at'), 80),
           'updated_at': _text(meta.get('updated_at', meta.get('finished_at', meta.get('created_at'))), 80),
           'simulated': meta.get('simulated') if type(meta.get('simulated')) is bool else None,
           'quarantined': _quarantined(directory, meta)}
    if row['quarantined']:
        row.update(state='quarantined', goal='Contenu en quarantaine · masqué', mode='unknown',
                   latest_frame=None, events=[], archive_status='hidden', agent_verdict=None,
                   scope_verdict=None, human_verdict=None, human_useful=None)
        return row
    report, request = _json(directory, 'report.json'), _json(directory, 'request.json')
    review, labels = _json(directory, 'agent-review.json'), _json(directory, 'labels.json')
    frames = _frames(directory, meta)
    mode = _text(meta.get('mode', request.get('mode', report.get('mode', 'act'))), 50)
    software = meta.get('software', request.get('software', report.get('software', source.software)))
    row.update(software=_text(software, 80) or source.software,
               goal=_text(meta.get('goal', request.get('goal', report.get('goal', meta.get('title', '')))), 3000),
               mode=mode, human_present=meta.get('human_present') is True,
               completion_reason=_text(meta.get('completion_reason', ''), 120),
               authentication_required=meta.get('authentication_required') is True,
               display_blocked=meta.get('display_blocked') is True,
               archive_status=_text(meta.get('export_status', 'pending'), 50),
               agent_verdict=_verdict(review.get('task_success_agent')),
               scope_verdict=_verdict(review.get('scope_compliance_agent')),
               human_verdict=_verdict(labels.get('task_success_user')) if labels.get('user_confirmed') is True else None,
               human_useful=labels.get('useful') if labels.get('user_confirmed') is True and isinstance(labels.get('useful'), (str, bool)) and labels.get('useful') in {True, False, 'yes', 'no', 'unknown'} else None,
               latest_frame=({'id': frames[-1]['id'], 'timestamp': frames[-1]['timestamp']} if frames else None),
               events=_events(directory, 30 if detail else 4))
    if detail:
        verification = _dict(report.get('verification'))
        raw_declared = report.get('declared')
        declared = raw_declared if isinstance(raw_declared, str) else _dict(raw_declared).get('summary', report.get('summary', ''))
        row.update(declared=_text(declared, 6000),
                   provider_state=_text(_dict(meta.get('provider_status')).get('status', meta.get('state')), 80),
                   observed=_text(verification.get('observed', ''), 6000),
                   verified=verification.get('satisfied') if type(verification.get('satisfied')) is bool else None,
                   rationale=[_text(x, 1600) for x in review.get('rationale', [])[:12]] if isinstance(review.get('rationale'), list) else [_text(review.get('rationale'))],
                   h_session_id=_text(meta.get('h_session_id', ''), 100),
                   frames=[{'id': f['id'], 'timestamp': f['timestamp']} for f in frames[-40:]])
    return row


def mount_control_tower(app, *, sources: Iterable[ControlTowerSource | dict], username: str,
                        password: str, prefix='/company/live'):
    """Mount a read-only dashboard; source roots are trusted server configuration."""
    if not username or len(password) < 16 or prefix != '/company/live':
        raise ValueError('Control tower requires private company credentials and its fixed route prefix.')
    registry = {}
    for item in sources:
        source = item if isinstance(item, ControlTowerSource) else ControlTowerSource(**item)
        if not SAFE_ID.fullmatch(source.id) or source.id in registry:
            raise ValueError('Control tower source identifiers must be unique and safe.')
        registry[source.id] = ControlTowerSource(source.id, _text(source.label, 80),
                                                Path(source.root).expanduser().resolve(), _text(source.software, 80))
    if not registry:
        raise ValueError('Control tower requires an explicitly configured episode source.')
    router = APIRouter(prefix=prefix)

    async def authenticated(request: Request):
        try:
            host = urlsplit('//' + request.headers.get('host', '')).hostname
        except ValueError:
            host = None
        if host not in {'localhost', '127.0.0.1', '::1'}:
            raise HTTPException(403, 'Console disponible uniquement sur le serveur local.')
        valid = False
        try:
            scheme, encoded = request.headers.get('authorization', '').split(' ', 1)
            user, secret = base64.b64decode(encoded, validate=True).decode().split(':', 1)
            valid = (scheme.lower() == 'basic' and hmac.compare_digest(user.encode(), username.encode())
                     and hmac.compare_digest(secret.encode(), password.encode()))
        except (ValueError, UnicodeError):
            pass
        if not valid:
            raise HTTPException(401, 'Authentification entreprise requise.', headers={
                'WWW-Authenticate': 'Basic realm="H-Companion entreprise", charset="UTF-8"', **HEADERS})
        expected = f'{request.url.scheme}://{request.headers.get("host", "")}'
        if (request.headers.get('origin') not in (None, expected)
                or request.headers.get('sec-fetch-site') == 'cross-site'):
            raise HTTPException(403, 'Origine refusée.')

    router.dependencies.append(Depends(authenticated))

    def directory(source_id, episode_id):
        if source_id not in registry or not SAFE_ID.fullmatch(episode_id):
            raise HTTPException(404, 'Session inconnue.')
        source = registry[source_id]
        base = source.root / 'episodes'
        folder = base / episode_id
        if base.is_symlink() or folder.is_symlink() or not folder.is_dir():
            raise HTTPException(404, 'Session inconnue.')
        return source, folder

    @router.get('', response_class=HTMLResponse)
    async def page():
        nonce = secrets.token_urlsafe(24)
        response = HTMLResponse(HTML.replace('__NONCE__', nonce), headers=HEADERS)
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; img-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; "
            f"script-src 'nonce-{nonce}'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
        return response

    @router.get('/data')
    async def data():
        rows = []
        for source in registry.values():
            base = source.root / 'episodes'
            if base.is_symlink() or not base.is_dir():
                continue
            for folder in base.iterdir():
                if folder.is_symlink() or not folder.is_dir() or not SAFE_ID.fullmatch(folder.name):
                    continue
                row = _record(source, folder)
                if row is not None:
                    rows.append(row)
        rows.sort(key=lambda row: row['created_at'], reverse=True)
        rows = rows[:MAX_EPISODES]
        return JSONResponse({'sources': [{'id': s.id, 'label': s.label, 'software': s.software} for s in registry.values()],
                             'sessions': rows, 'limit': MAX_EPISODES}, headers=HEADERS)

    @router.get('/sessions/{source_id}/{episode_id}')
    async def session(source_id: str, episode_id: str):
        source, folder = directory(source_id, episode_id)
        row = _record(source, folder, detail=True)
        if row is None:
            raise HTTPException(404, 'Session inconnue.')
        return JSONResponse(row, headers=HEADERS)

    @router.get('/frames/{source_id}/{episode_id}/{frame_id}')
    async def frame(source_id: str, episode_id: str, frame_id: str):
        _, folder = directory(source_id, episode_id)
        if not SAFE_ID.fullmatch(frame_id):
            raise HTTPException(404, 'Écran indisponible.')
        match = next((item for item in _frames(folder, _json(folder, 'episode.json')) if item['id'] == frame_id), None)
        if match is None:
            raise HTTPException(404, 'Écran indisponible.')
        file = folder / match['path']
        try:
            if file.stat().st_size > MAX_IMAGE:
                raise ValueError('Too large')
            content = file.read_bytes()
        except (OSError, ValueError):
            raise HTTPException(404, 'Écran indisponible.') from None
        media = ('image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else
                 'image/jpeg' if content.startswith(b'\xff\xd8\xff') else
                 'image/webp' if content[:4] == b'RIFF' and content[8:12] == b'WEBP' else None)
        if (len(content) > MAX_IMAGE or media is None
                or not hmac.compare_digest(hashlib.sha256(content).hexdigest(), match['sha256'])):
            raise HTTPException(404, 'Écran indisponible.')
        return Response(content, media_type=media, headers=HEADERS)

    app.include_router(router)
    return router


HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tour de contrôle · H-Companion</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f3f7f4;color:#173b33;font:15px system-ui,sans-serif}button,select,input{font:inherit}button,select{border:1px solid #c6d6cd;border-radius:9px;padding:9px 13px;background:white;color:inherit}button{cursor:pointer}a{color:#08735e}main{max-width:1680px;margin:auto;padding:20px 24px}header,nav,.toolbar,.title,.card-head,.stats{display:flex;align-items:center;gap:18px;flex-wrap:wrap}header{justify-content:space-between}nav{font-size:14px}h1{font-size:30px;letter-spacing:-1px;margin:16px 0 5px}h2{font-size:19px;margin:0}p{line-height:1.5}.subtitle,.muted{color:#5a7469}.subtitle{margin:7px 0 10px}.title{justify-content:space-between}.live-dot{width:8px;height:8px;border-radius:50%;background:#169f77;display:inline-block;margin-right:6px}.stats{gap:12px;margin:12px 0}.stat{flex:1;min-width:150px;background:white;border:1px solid #d7e3db;border-radius:12px;padding:8px 16px}.stat strong{display:block;font-size:22px;margin-top:2px}.toolbar{padding:10px 0;border-top:1px solid #d7e3db;border-bottom:1px solid #d7e3db;margin-bottom:16px}.toolbar label{display:flex;gap:7px;align-items:center}.work{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:18px;align-items:start}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.card,.detail{background:#fff;border:1px solid #d3e1d8;border-radius:14px;overflow:hidden}.card{cursor:pointer;transition:border-color .15s}.card.selected{border:2px solid #08735e}.card-head{justify-content:space-between;padding:10px 12px;gap:8px}.source{font-weight:700}.badge{font-size:12px;padding:4px 8px;border-radius:20px;background:#edf2ee;color:#466155;white-space:nowrap}.badge.live{background:#d8f2e6;color:#07573d}.badge.warn{background:#fff0cf;color:#7d5210}.badge.bad{background:#fae6e3;color:#923b2f}.screen{background:#e7eee9;aspect-ratio:16/9;display:grid;place-items:center;position:relative;overflow:hidden}.screen img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}.screen .placeholder{padding:28px;text-align:center;color:#657c71;font-size:13px}.screen .stamp{position:absolute;bottom:9px;right:9px;background:#16382dd9;color:white;padding:4px 7px;border-radius:5px;font-size:11px}.card .screen{aspect-ratio:16/7}.card-body{padding:10px 12px}.card .goal{font-size:13px;margin:6px 0 8px;line-height:1.35}.card .mode{font-size:11px}.card .last-event{font-size:12px}.card .badge{white-space:normal;max-width:190px}.goal{margin:9px 0 12px;line-height:1.45;font-weight:600;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.mode{font-size:12px;color:#557266}.last-event{font-size:13px;color:#64796e;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}.card-footer{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.detail{padding:21px;position:sticky;top:20px;max-height:calc(100vh - 40px);overflow:auto}.detail h3{font-size:14px;margin:23px 0 10px}.detail p{margin:9px 0;overflow-wrap:anywhere}.detail .screen{border-radius:9px;margin:15px 0;cursor:zoom-in}.detail .screen img{max-height:260px}.detail .goal{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}.timeline{padding:0;list-style:none;margin:9px 0}.timeline li{padding:10px 0 10px 14px;border-left:2px solid #d7e3db;font-size:13px;overflow-wrap:anywhere}.timeline time{display:block;font-size:11px;color:#789084;margin-bottom:3px}.verdicts{display:grid;grid-template-columns:1fr 1fr;gap:9px}.verdicts div{background:#f3f7f4;padding:12px;border-radius:8px;font-size:12px}.verdicts strong{display:block;margin-top:5px;font-size:14px}.empty{padding:45px 20px;border:1px dashed #c4d6c9;border-radius:12px;text-align:center;color:#658075}.error{color:#9b3b2b;font-size:13px}.small{font-size:12px}.tag-real{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#7a6b49}.detail code{font-size:11px;overflow-wrap:anywhere}.history{display:none}.footer{font-size:12px;color:#6d8377;margin:24px 0 5px}dialog{border:0;border-radius:15px;padding:16px;background:#eef4ef;max-width:95vw}dialog::backdrop{background:#06291ccc}dialog img{max-width:90vw;width:1200px;height:78vh;object-fit:contain;background:#dce7df}dialog header{padding-bottom:10px}.sr{position:absolute;left:-10000px}@media(max-width:1380px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:1120px){.work{grid-template-columns:1fr 340px}.grid{grid-template-columns:1fr}}@media(max-width:760px){main{padding:20px 14px}.work{grid-template-columns:1fr}.detail{position:static;max-height:none}.grid{grid-template-columns:1fr}h1{font-size:29px}.stats{display:grid;grid-template-columns:1fr 1fr}.stat{min-width:0;padding:13px}.toolbar{gap:12px}header{gap:12px}.screen,.card .screen{aspect-ratio:16/10}dialog img{height:65vh}}</style></head>
<body><main><header><strong>H-Companion · Entreprise</strong><nav><a href="/company">Configuration</a><a href="/company/documents">Documentation</a><a href="/company/sessions">Sessions et retours</a><a href="/company/live" aria-current="page">Tour de contrôle</a></nav></header>
<div class="title"><div><h1>Les sessions, en direct.</h1><p class="subtitle">Suivez les questions, les écrans reçus et les résultats de chaque intervention.</p></div><span id="connection" class="small"><i class="live-dot"></i>Connexion…</span></div>
<section class="stats" aria-label="Activité"><div class="stat">En cours<strong id="live-count">—</strong></div><div class="stat">Sessions réelles<strong id="real-count">—</strong></div><div class="stat">Terminées<strong id="done-count">—</strong></div><div class="stat">Retours humains<strong id="human-count">—</strong></div></section>
<div class="toolbar"><label>Logiciel <select id="software"><option value="">Tous</option></select></label><label><input id="active-only" type="checkbox"> Seulement en cours</label><button id="refresh" type="button">Actualiser</button><span id="visible-count" class="small muted"></span><span id="failure" class="error" role="status"></span></div>
<div class="work"><section id="cards" class="grid" aria-label="Sessions"></section><aside id="detail" class="detail"><h2>Choisir une session</h2><p class="muted">Sélectionnez une session pour lire la demande, les événements et les verdicts distincts.</p></aside></div>
<p class="footer">Les tests exécutés par un agent ne remplacent pas une séance de coaching humain. Les écrans d’authentification et les contenus en quarantaine restent masqués.</p></main>
<dialog id="preview"><header><strong id="preview-title">Écran reçu</strong><button id="close-preview" type="button">Fermer</button></header><img id="preview-image" alt="Dernier écran autorisé de la session"></dialog>
<script nonce="__NONCE__">'use strict';
const endpoint='/company/live', terminal=new Set(['resolved','escalated','completed','failed','failure','stopped','preflight_failed','cancelled','interrupted','timed_out','not_started','quarantined']), activeStates=new Set(['queued_local','starting','running','awaiting_input','executing','verifying','queued','pending','awaiting_auth','awaiting_2fa','awaiting_user','awaiting_approval']);
const stateNames={running:'En cours',executing:'En cours',verifying:'Vérification',queued:'En attente',queued_local:'En attente locale',starting:'Démarrage',pending:'En attente',awaiting_input:'Attend une réponse',not_started:'Non démarré',start_uncertain:'Démarrage à vérifier',termination_unconfirmed:'Arrêt à confirmer',awaiting_auth:'Connexion à préparer',awaiting_2fa:'Validation demandée',awaiting_user:'Attend l’utilisateur',awaiting_approval:'Attend un accord',resolved:'Résolu · moteur',completed:'Terminé',escalated:'À examiner',failed:'Échec technique',failure:'Échec',stopped:'Arrêté',interrupted:'Interrompu',timed_out:'Délai atteint',quarantined:'Quarantaine',unknown:'État inconnu'};
const verdictNames={success:'Réussi',partial:'Partiel',failure:'Échec',failed:'Échec',unknown:'Non évalué'};
let records=[],selected=null,pending=false,detailPending=false,selectionVersion='',dialogKey=null;
const byId=id=>document.getElementById(id), key=r=>r.source_id+':'+r.id;
function el(tag,className,text){const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=text;return n}
function time(v){if(!v)return 'Horodatage indisponible';const d=new Date(v);return Number.isNaN(d.getTime())?'Horodatage indisponible':d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
function frameUrl(r){return r.latest_frame?endpoint+'/frames/'+[r.source_id,r.id,r.latest_frame.id].map(encodeURIComponent).join('/'):null}
function modeLabel(r){if(['guide','coach','coaching'].includes(r.mode))return r.human_present?'Coaching · utilisateur présent':'Coaching · test sans utilisateur';return 'Exécution agent · test'}
function badge(r){const answered=r.state==='interrupted'&&r.completion_reason==='answered_then_cancelled_for_terminal_confirmation';const b=el('span','badge',r.authentication_required?'Connexion requise':answered?'Réponse reçue · session fermée':stateNames[r.state]||r.state);if(r.authentication_required)b.classList.add('warn');else if(activeStates.has(r.state))b.classList.add('live');else if(['escalated','start_uncertain','termination_unconfirmed'].includes(r.state))b.classList.add('warn');else if(['failed','failure','quarantined'].includes(r.state))b.classList.add('bad');return b}
function screen(r){const box=el('div','screen'),url=frameUrl(r);if(url){const img=el('img');img.alt='Dernier écran autorisé';img.src=url;img.loading='lazy';box.append(img,el('span','stamp',time(r.latest_frame.timestamp)));box.addEventListener('click',e=>{e.stopPropagation();showPreview(r)})}else{box.append(el('p','placeholder',r.quarantined?'Contenu masqué':r.authentication_required?'Connexion requise · écran masqué':r.display_blocked?'Écran indisponible pour cette session':(['auth','login','credentials','awaiting_auth','awaiting_2fa','authentication'].includes(r.phase)?'Authentification · écran masqué':'Aucun écran autorisé reçu')))}return box}
function showPreview(r){const url=frameUrl(r);if(!url)return;dialogKey=key(r);byId('preview-title').textContent=r.source_label+' · '+time(r.latest_frame.timestamp);byId('preview-image').src=url;byId('preview').showModal()}
byId('close-preview').onclick=()=>byId('preview').close();
function render(){const active=records.filter(r=>activeStates.has(r.state));byId('live-count').textContent=active.length;byId('real-count').textContent=records.filter(r=>r.simulated===false&&!r.quarantined).length;byId('done-count').textContent=records.filter(r=>terminal.has(r.state)&&!r.quarantined).length;byId('human-count').textContent=records.filter(r=>r.human_verdict!==null&&!r.quarantined).length;
 const software=byId('software'),old=software.value,options=[...new Set(records.map(r=>r.software).filter(Boolean))].sort();if(JSON.stringify(options)!==software.dataset.options){software.replaceChildren(el('option','', 'Tous'));software.firstChild.value='';for(const s of options){const o=el('option','',s);o.value=s;software.append(o)}software.value=old;software.dataset.options=JSON.stringify(options)}
 const visible=records.filter(r=>(!software.value||r.software===software.value)&&(!byId('active-only').checked||activeStates.has(r.state)));byId('visible-count').textContent=visible.length+' session(s) affichée(s)';const grid=byId('cards'),retained=new Set();
 for(const r of visible){const k=key(r);retained.add(k);let node=[...grid.children].find(x=>x.dataset.key===k),signature=JSON.stringify(r);if(!node||node.dataset.version!==signature){const card=el('article','card');card.dataset.key=k;card.dataset.version=signature;card.tabIndex=0;card.setAttribute('aria-label',r.source_label+' · '+r.goal);const head=el('div','card-head');head.append(el('span','source',r.software||r.source_label),badge(r));const body=el('div','card-body');body.append(el('div','mode',modeLabel(r)),el('p','goal',r.goal||'Demande non renseignée'));const last=r.events&&r.events[r.events.length-1];body.append(el('div','last-event',last?time(last.timestamp)+' · '+last.message:'En attente d’événements'));const foot=el('div','card-footer');foot.append(el('span','tag-real',r.simulated===true?'Simulation':r.simulated===false?'Session réelle H':'Provenance à vérifier'),el('span','small muted',r.source_label));body.append(foot);card.append(head,screen(r),body);card.onclick=()=>select(r);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(r)}};if(node)node.replaceWith(card);else grid.append(card);node=card}node.classList.toggle('selected',k===selected);grid.append(node)}
 for(const node of [...grid.children])if(!retained.has(node.dataset.key))node.remove();if(!visible.length){const empty=el('div','empty','Aucune session dans cette sélection. Les nouvelles interventions apparaîtront ici.');grid.append(empty)}
 if(byId('preview').open){const r=records.find(r=>key(r)===dialogKey),url=r&&frameUrl(r);if(!url){byId('preview').close();byId('preview-image').removeAttribute('src')}else if(byId('preview-image').getAttribute('src')!==url){byId('preview-image').src=url;byId('preview-title').textContent=r.source_label+' · '+time(r.latest_frame.timestamp)}}
}
function select(r){selected=key(r);selectionVersion='';render();loadDetail()}
function renderDetail(r){const signature=JSON.stringify(r);if(signature===selectionVersion)return;selectionVersion=signature;const area=byId('detail');area.replaceChildren(el('h2','',r.software||r.source_label),el('p','small muted',modeLabel(r)),badge(r),el('p','goal',r.goal),screen(r));const verdicts=el('div','verdicts');for(const [label,value] of [['Revue IA',verdictNames[r.agent_verdict]||'À relire'],['Retour humain',verdictNames[r.human_verdict]||'Non recueilli'],['Périmètre',verdictNames[r.scope_verdict]||'Non évalué'],['Archive',({complete:'Complète',recorded:'Enregistrée',partial:'Partielle',pending:'En attente',incomplete:'Incomplète',hidden:'Masquée',failed:'Échec d’archivage'})[r.archive_status]||r.archive_status||'En attente']]){const box=el('div','',label);box.append(el('strong','',value));verdicts.append(box)}area.append(verdicts);if(r.provider_state)area.append(el('p','small muted','État fournisseur : '+r.provider_state));if(r.goal&&r.goal.length>220){const full=el('details');full.append(el('summary','','Lire la demande complète'),el('p','small',r.goal));area.append(full)}
 if(r.declared){area.append(el('h3','','Réponse de l’agent'),el('p','small',r.declared))}if(r.observed){area.append(el('h3','','Vérification observée'),el('p','small',r.observed))}if(r.rationale&&r.rationale.some(Boolean)){const details=el('details');details.append(el('summary','','Lire la revue IA'));const ul=el('ul','small');for(const p of r.rationale.filter(Boolean))ul.append(el('li','',p));details.append(ul);area.append(details)}area.append(el('h3','','Derniers événements'));const list=el('ol','timeline');for(const ev of [...(r.events||[])].reverse()){const li=el('li');li.append(el('time','',time(ev.timestamp)),el('span','',ev.message||stateNames[ev.state]||ev.type));list.append(li)}if(!list.children.length)list.append(el('li','muted','Aucun événement public disponible.'));area.append(list,el('p','small muted','Session : '+r.id));}
async function loadDetail(){if(!selected||detailPending)return;detailPending=true;const requested=selected,[source,id]=selected.split(':');try{const response=await fetch(endpoint+'/sessions/'+[source,id].map(encodeURIComponent).join('/'),{cache:'no-store',credentials:'same-origin'});if(!response.ok)throw Error();const value=await response.json();if(selected===requested)renderDetail(value)}catch{if(selected===requested)byId('detail').replaceChildren(el('h2','','Session momentanément indisponible'),el('p','muted','La prochaine actualisation réessaiera.'))}finally{detailPending=false}}
async function refresh(){if(pending)return;pending=true;try{const response=await fetch(endpoint+'/data',{cache:'no-store',credentials:'same-origin'});if(!response.ok)throw Error();const data=await response.json();records=data.sessions||[];render();byId('connection').textContent='● Actualisé à '+new Date().toLocaleTimeString('fr-FR');byId('failure').textContent='';await loadDetail()}catch{byId('connection').textContent='Actualisation interrompue';byId('failure').textContent='Connexion au portail indisponible. Les écrans affichés peuvent être anciens.'}finally{pending=false}}
byId('refresh').onclick=refresh;byId('software').onchange=render;byId('active-only').onchange=render;refresh();setInterval(refresh,2000);
</script></body></html>'''
