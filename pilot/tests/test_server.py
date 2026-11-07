"""Offline adapter lifecycle tests. No microphone, desktop, model or network calls."""
import copy
import io
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import wave

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hcs_agent.backend import MockBackend
from pilot.server import create_app

TOKEN = 'offline-test-token-not-a-real-secret'
AUTH = {'Authorization': 'Bearer ' + TOKEN}


class StoreSpy:
    def __init__(self):
        self.cases, self.events = [], []

    def add_case(self, report):
        self.cases.append(copy.deepcopy(report))

    def add_event(self, event):
        self.events.append(copy.deepcopy(event))


def wav_bytes(seconds=.2):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b'\0\0' * int(16000 * seconds))
    return buffer.getvalue()


def factory(tmp_path, **kwargs):
    return create_app(private_root=tmp_path, token=TOKEN,
                      backend=kwargs.pop('backend', MockBackend(step_delay_s=0)), **kwargs)


def create(client, number='01', **extra):
    return client.post('/pilot/episodes', headers=AUTH,
                       json={'scenario_id': number, 'goal': 'Retrouve le produit sans modifier les données.', **extra})


def finish(client, sid):
    assert client.post(f'/interventions/{sid}/approve', headers=AUTH, json={'approved': True}).status_code == 200
    for _ in range(200):
        result = client.get(f'/pilot/episodes/{sid}', headers=AUTH).json()
        if result.get('report_ready') and result['pilot']['export_status'] != 'exporting':
            return result
        time.sleep(.01)
    pytest.fail('offline intervention did not finish')


def test_auth_covers_inherited_http_websocket_and_bypass(tmp_path):
    with TestClient(factory(tmp_path)) as client:
        assert client.get('/pilot/status').status_code == 401
        assert client.get('/health').status_code == 401
        assert client.get('/pilot/scenarios', headers={**AUTH, 'Origin': 'https://attacker.invalid'}).status_code == 401
        assert client.post('/interventions', headers=AUTH, json={}).status_code == 403
        assert client.post('/interventions/session/feedback', headers=AUTH, json={}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/interventions/unknown/ws'):
                pass
        status = client.get('/pilot/status', headers=AUTH).json()
        assert status['simulated'] is True and status['busy'] is False
        assert status['transcription']['ready'] is False


def test_catalog_only_contains_prompt_not_oracle(tmp_path):
    with TestClient(factory(tmp_path)) as client:
        cards = client.get('/pilot/scenarios', headers=AUTH).json()
        assert [c['id'] for c in cards] == [f'{i:02d}' for i in range(1, 11)]
        assert '10 €' not in cards[0]['prompt']
        assert 'Réussite attendue' not in json.dumps(cards)
        assert cards[5]['depends_on'] == '05'
        assert cards[4]['requires_reference'] is True


def test_exact_procedure_approval_and_single_active(tmp_path):
    with TestClient(factory(tmp_path)) as client:
        made = create(client).json()
        sid = made['session_id']
        assert made['state'] == 'awaiting_approval'
        assert made['request']['procedure_id'] == 'odoo_inventory_read_product'
        assert made['request']['mode'] == 'act'
        assert made['steps'] == []
        assert create(client, '02').status_code == 409
        assert client.get('/pilot/status', headers=AUTH).json()['busy'] is True
        result = finish(client, sid)
        assert result['state'] == 'resolved'
        assert result['report']['simulated'] is True
        assert result['pilot']['export_status'] == 'skipped_simulated'
        assert create(client, '02').status_code == 201


def test_invalid_scenario_empty_goal_reference_and_workflow_dependencies(tmp_path):
    with TestClient(factory(tmp_path)) as client:
        assert create(client, '99').status_code == 422
        assert create(client, goal='  ').status_code == 422
        assert create(client, '05').status_code == 422
        assert create(client, '05', run_reference='../bad').status_code == 422
        assert create(client, '06', run_reference='TEST-001').status_code == 409
        draft = create(client, '05', run_reference='TEST-001').json()
        finish(client, draft['session_id'])
        assert create(client, '06', run_reference='TEST-002').status_code == 409
        assert create(client, '06', run_reference='TEST-001', workflow_id='different').status_code == 409
        assert create(client, '06', run_reference='TEST-001').status_code == 201


def test_voice_and_unknown_feedback_persist_without_rewriting_verification(tmp_path):
    store = StoreSpy()
    speech_calls = []

    def speech(path, mime):
        speech_calls.append((path, mime))
        return {'transcript': "Je n'ai pas vu, je ne sais pas si c'est utile.", 'provider': 'fake-local'}

    with TestClient(factory(tmp_path, transcriber=speech, store=store)) as client:
        request_audio = client.post('/pilot/audio?purpose=request', headers={**AUTH, 'Content-Type': 'audio/wav'},
                                    content=wav_bytes()).json()
        made = create(client, request_audio_id=request_audio['audio_id']).json()
        sid = made['session_id']
        assert client.post('/pilot/audio?purpose=feedback', headers={**AUTH, 'Content-Type': 'audio/wav'},
                           content=wav_bytes()).status_code == 409
        assert client.post(f'/pilot/episodes/{sid}/feedback', headers=AUTH,
                           json={'task_success_user': 'unknown', 'useful': 'unknown'}).status_code == 409
        result = finish(client, sid)
        original_verification = result['report']['verification']
        feedback_audio = client.post('/pilot/audio?purpose=feedback', headers={**AUTH, 'Content-Type': 'audio/wav'},
                                     content=wav_bytes()).json()
        response = client.post(f'/pilot/episodes/{sid}/feedback', headers=AUTH,
            json={'task_success_user': 'unknown', 'useful': 'unknown', 'comment': feedback_audio['transcript'],
                  'audio_id': feedback_audio['audio_id'], 'allow_training': False})
        assert response.status_code == 200
        final = response.json()
        assert final['report']['verification'] == original_verification
        assert final['report']['feedback']['useful'] is None
        assert final['pilot']['feedback']['task_success_user'] == 'unknown'
        assert final['pilot']['feedback']['raw_transcript'] == feedback_audio['transcript']
        assert final['pilot']['feedback']['include_for_training'] is False
        assert store.cases[-1]['feedback']['comment'] == feedback_audio['transcript']
        assert store.events and all(e['simulated'] is True for e in store.events)
        assert len(speech_calls) == 2
        immutable = json.loads((tmp_path/'episodes'/sid/'request.json').read_text())
        assert immutable['audio']['transcript'] == request_audio['transcript']
        assert all(path.stat().st_mode & 0o077 == 0 for path in tmp_path.rglob('*') if path.is_file())


def test_audio_limits_and_type_rejected_before_transcription(tmp_path):
    calls = []

    def speech(path, mime):
        calls.append(path)
        return 'spoken request'

    with TestClient(factory(tmp_path, transcriber=speech)) as client:
        assert client.post('/pilot/audio?purpose=request', headers={**AUTH, 'Content-Type': 'audio/wav'},
                           content=b'not audio').status_code == 422
        assert client.post('/pilot/audio?purpose=request', headers={**AUTH, 'Content-Type': 'audio/wav'},
                           content=wav_bytes(90.01)).status_code == 422
        assert client.post('/pilot/audio?purpose=request', headers={**AUTH, 'Content-Type': 'audio/wav'},
                           content=b'x' * (12 * 1024 * 1024 + 1)).status_code == 413
        assert client.post('/pilot/audio?purpose=request', headers={**AUTH, 'Content-Type': 'text/plain'},
                           content=b'hello').status_code == 415
        assert not calls
        assert list((tmp_path/'audio').glob('*')) == []


def test_audio_purpose_and_path_cannot_be_reused_in_wrong_slot(tmp_path):
    with TestClient(factory(tmp_path, transcriber=lambda p, m: 'feedback only')) as client:
        recording = client.post('/pilot/audio?purpose=feedback', headers={**AUTH, 'Content-Type': 'audio/wav'},
                                 content=wav_bytes()).json()
        assert create(client, request_audio_id=recording['audio_id']).status_code == 422
        assert create(client, request_audio_id='../../outside').status_code == 422
        assert client.get('/pilot/episodes/unknown', headers=AUTH).status_code == 404


def test_completed_episode_can_be_read_after_restart(tmp_path):
    with TestClient(factory(tmp_path)) as client:
        sid = create(client).json()['session_id']
        before = finish(client, sid)
        client.post(f'/pilot/episodes/{sid}/feedback', headers=AUTH,
                    json={'task_success_user': 'partial', 'useful': 'unknown', 'comment': 'pas tout vu'})
    with TestClient(factory(tmp_path)) as client:
        restored = client.get(f'/pilot/episodes/{sid}', headers=AUTH).json()
        assert restored['restored_read_only'] is True
        assert restored['report']['verification'] == before['report']['verification']
        assert restored['pilot']['feedback']['comment'] == 'pas tout vu'
        assert client.post(f'/pilot/episodes/{sid}/feedback', headers=AUTH,
                           json={'task_success_user': 'success', 'useful': 'yes'}).status_code == 409


def test_export_callback_never_called_for_simulated_run(tmp_path):
    calls = []
    with TestClient(factory(tmp_path, exporter=lambda *args: calls.append(args))) as client:
        result = finish(client, create(client).json()['session_id'])
        assert result['pilot']['export_status'] == 'skipped_simulated'
        assert calls == []


def test_stub_export_and_feedback_copies_latest_labels(tmp_path):
    # A fake non-simulated backend exercises dispatch only, never calls real H.
    class FakeRealBackend(MockBackend):
        simulated = False

    def export(report_path, archive_dir):
        archive_dir.mkdir()
        (archive_dir/'report.json').write_text(report_path.read_text())
        return {'archive_complete': True, 'ready_for_sft': False}

    with TestClient(factory(tmp_path, backend=FakeRealBackend(step_delay_s=0), exporter=export)) as client:
        sid = create(client).json()['session_id']
        result = finish(client, sid)
        assert result['pilot']['export_status'] == 'complete'
        client.post(f'/pilot/episodes/{sid}/feedback', headers=AUTH,
                    json={'task_success_user': 'success', 'useful': 'yes', 'comment': 'clear', 'allow_training': True})
        labels = json.loads((tmp_path/'archives'/sid/'labels.json').read_text())
        report = json.loads((tmp_path/'archives'/sid/'report.json').read_text())
        assert labels['allow_training'] is True and labels['include_for_training'] is False
        assert report['feedback']['useful'] is True
        assert (tmp_path/'archives'/sid/'procedure.json').exists()


def test_webm_without_duration_decodes_bounded_audio_and_enforces_duration(tmp_path, monkeypatch):
    import pilot.server as server
    duration = [.2]
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0].endswith('ffprobe'):
            return SimpleNamespace(stdout=b'{"streams":[{"codec_type":"audio"}],"format":{}}')
        assert command[command.index('-t') + 1] == '90.1'
        assert kwargs['timeout'] == 20
        return SimpleNamespace(stdout=b'\0' * int(duration[0] * 32000))

    monkeypatch.setattr(server.shutil, 'which', lambda name: '/fake/' + name)
    monkeypatch.setattr(server.subprocess, 'run', run)
    transcribed = []

    def speech(path, mime):
        transcribed.append(mime)
        return 'spoken request'

    with TestClient(factory(tmp_path, transcriber=speech)) as client:
        response = client.post('/pilot/audio?purpose=request',
            headers={**AUTH, 'Content-Type': 'audio/webm;codecs=opus'}, content=b'stub audio container')
        assert response.status_code == 200
        duration[0] = 90.1
        response = client.post('/pilot/audio?purpose=request',
            headers={**AUTH, 'Content-Type': 'audio/webm'}, content=b'stub overlong container')
        assert response.status_code == 422
        assert transcribed == ['audio/webm']
        assert len(calls) == 4


def test_feedback_racing_export_is_preserved_in_archive(tmp_path):
    class FakeRealBackend(MockBackend):
        simulated = False

    entered, release = threading.Event(), threading.Event()

    def export(report_path, archive_dir):
        old_report = report_path.read_text()
        entered.set()
        assert release.wait(3)
        archive_dir.mkdir()
        (archive_dir/'report.json').write_text(old_report)
        return {'archive_complete': True}

    with TestClient(factory(tmp_path, backend=FakeRealBackend(step_delay_s=0), exporter=export)) as client:
        sid = create(client).json()['session_id']
        client.post(f'/interventions/{sid}/approve', headers=AUTH, json={'approved': True})
        try:
            assert entered.wait(2)
            result = client.post(f'/pilot/episodes/{sid}/feedback', headers=AUTH,
                json={'task_success_user': 'partial', 'useful': 'unknown', 'comment': 'Concurrent oral feedback'})
            assert result.status_code == 200
            assert result.json()['pilot']['export_status'] == 'exporting'
        finally:
            release.set()
        for _ in range(200):
            if client.get(f'/pilot/episodes/{sid}', headers=AUTH).json()['pilot']['export_status'] == 'complete':
                break
            time.sleep(.01)
        labels = json.loads((tmp_path/'archives'/sid/'labels.json').read_text())
        report = json.loads((tmp_path/'archives'/sid/'report.json').read_text())
        assert labels['task_success_user'] == 'partial'
        assert report['feedback']['comment'] == 'Concurrent oral feedback'


def test_transcriber_failure_keeps_private_audio_and_does_not_leak_exception(tmp_path):
    def speech(path, mime):
        raise RuntimeError('sensitive provider diagnostic')

    with TestClient(factory(tmp_path, transcriber=speech)) as client:
        response = client.post('/pilot/audio?purpose=feedback',
            headers={**AUTH, 'Content-Type': 'audio/wav'}, content=wav_bytes())
        assert response.status_code == 502
        assert 'sensitive' not in response.text
        records = list((tmp_path/'audio').glob('*.json'))
        assert len(records) == 1
        meta = json.loads(records[0].read_text())
        assert meta['status'] == 'failed' and meta['error'] == 'RuntimeError'
        assert (tmp_path/'audio'/meta['file']).stat().st_mode & 0o077 == 0


def test_text_feedback_persists_to_actual_tom_store_without_audio(tmp_path):
    Store = pytest.importorskip('hcs_backend.store').Store
    store = Store(':memory:')
    with TestClient(factory(tmp_path, store=store)) as client:
        sid = create(client).json()['session_id']
        finish(client, sid)
        response = client.post(f'/pilot/episodes/{sid}/feedback', headers=AUTH,
            json={'task_success_user': 'unknown', 'useful': 'unknown', 'comment': 'Je n’ai pas vu.'})
        assert response.status_code == 200
        labels = response.json()['pilot']['feedback']
        assert labels['audio'] is None and labels['raw_transcript'] is None
        assert labels['comment'] == 'Je n’ai pas vu.'
        assert response.json()['pilot']['store_status'] == 'saved'
        cases = store.list_cases()
        assert len(cases) == 1
        assert cases[0].report['feedback']['comment'] == labels['comment']
        assert cases[0].report['feedback']['useful'] is None
        assert store.list_events(sid)


def test_resolved_without_verified_postcondition_cannot_unlock_next_scenario(tmp_path):
    with TestClient(factory(tmp_path)) as client:
        sid = create(client, '05', run_reference='TEST-VERIFY').json()['session_id']
        finish(client, sid)
        path = tmp_path/'episodes'/sid/'report.json'
        report = json.loads(path.read_text())
        assert report['status'] == 'resolved'
        report['verification']['satisfied'] = False
        path.write_text(json.dumps(report))
        assert create(client, '06', run_reference='TEST-VERIFY').status_code == 409
