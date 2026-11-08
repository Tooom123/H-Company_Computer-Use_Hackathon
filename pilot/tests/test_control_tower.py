"""Live views must never turn a private episode folder into a file server."""
import base64
import hashlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from pilot.control_tower import mount_control_tower

PASSWORD = 'test-control-tower-private-password'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=')


def write(folder, name, value):
    (folder / name).write_text(json.dumps(value), encoding='utf-8')


def episode(root, sid='sess_live', *, phase='working', state='running', goal='Find the session quota'):
    folder = root / 'episodes' / sid
    folder.mkdir(parents=True)
    write(folder, 'episode.json', {'goal': goal, 'state': state, 'phase': phase,
        'simulated': False, 'source': 'h-company', 'mode': 'act', 'created_at': '2026-11-07T22:00:00Z',
        'updated_at': '2026-11-07T22:00:02Z', 'export_status': 'pending', 'h_session_id': 'owned-h-session'})
    write(folder, 'request.json', {'software': 'H Company', 'api_key': 'private-request-secret'})
    return folder


def frame(folder, *, grant=True, phase='working', content=PNG, frame_id='000001'):
    (folder / 'frames').mkdir(exist_ok=True)
    path = f'frames/{frame_id}.png'
    (folder / path).write_bytes(content)
    item = {'id': frame_id, 'path': path, 'index': 1, 'timestamp': '2026-11-07T22:00:03Z',
            'sha256': hashlib.sha256(content).hexdigest(), 'display_allowed': grant, 'phase': phase,
            'remote_url': 'https://private.invalid/image?X-Amz-Signature=private-image-token'}
    write(folder, 'frames.json', {'frames': [item]})
    return item


def client(roots):
    app = FastAPI()
    mount_control_tower(app, sources=[{'id': key, 'label': key.title(), 'root': path, 'software': key}
                                      for key, path in roots.items()], username='support', password=PASSWORD)
    result = TestClient(app, base_url='http://127.0.0.1:8767')
    result.auth = ('support', PASSWORD)
    return result


def test_shared_cloud_directory_preserves_each_product_identity(tmp_path):
    folder = episode(tmp_path)
    write(folder, 'episode.json', {'source': 'comfyui', 'state': 'interrupted',
                                  'goal': 'Inspect node help', 'simulated': False})
    write(folder, 'request.json', {'source': 'comfyui'})
    c = client({'cloud': tmp_path})
    result = c.get('/company/live/sessions/cloud/sess_live')
    assert result.status_code == 200
    assert result.json()['software'] == 'comfyui'


@pytest.mark.parametrize('route', ['', '/data', '/sessions/cloud/sess_live', '/frames/cloud/sess_live/000001', '/assets/fonts/PlusJakartaSans.ttf'])
def test_all_routes_require_company_auth(tmp_path, route):
    folder = episode(tmp_path)
    frame(folder)
    c = client({'cloud': tmp_path})
    assert c.get('/company/live' + route, auth=None).status_code == 401
    assert c.get('/company/live' + route, auth=('support', 'wrong')).status_code == 401
    assert c.get('/company/live' + route + '?token=' + PASSWORD, auth=None).status_code == 401
    assert c.get('/company/live' + route, auth=None, headers={'Authorization': 'Bearer ' + PASSWORD}).status_code == 401


@pytest.mark.parametrize('headers', [{'Host': 'external.invalid'}, {'Host': '[invalid'},
    {'Origin': 'https://external.invalid'}, {'Sec-Fetch-Site': 'cross-site'}])
def test_browser_origin_and_host_are_checked(tmp_path, headers):
    c = client({'cloud': tmp_path})
    assert c.get('/company/live/data', headers=headers).status_code == 403


def test_brand_fonts_are_local_allowlisted_and_same_origin(tmp_path):
    c = client({'cloud': tmp_path})
    page = c.get('/company/live')
    assert "font-src 'self'" in page.headers['content-security-policy']
    assert 'fonts.googleapis.com' not in page.text and 'fonts.gstatic.com' not in page.text
    for name in ['PlusJakartaSans.ttf', 'FiraCode.ttf', 'Caveat.ttf']:
        result = c.get('/company/live/assets/fonts/' + name)
        assert result.status_code == 200 and result.content[:4] == b'\x00\x01\x00\x00'
        assert result.headers['content-type'] == 'font/ttf'
        assert result.headers['cross-origin-resource-policy'] == 'same-origin'
    assert c.get('/company/live/assets/fonts/README.md').status_code == 404
    assert c.get('/company/live/assets/fonts/..%2Fepisode.json').status_code == 404


def test_live_metadata_and_image_are_bounded_and_do_not_expose_resource_secrets(tmp_path):
    folder = episode(tmp_path, goal='<script>alert(1)</script> Find quota')
    frame(folder)
    c = client({'cloud': tmp_path})
    page = c.get('/company/live')
    assert page.status_code == 200
    assert PASSWORD not in page.text and '<script>alert(1)</script>' not in page.text
    assert "script-src 'nonce-" in page.headers['content-security-policy']
    assert "frame-ancestors 'none'" in page.headers['content-security-policy']
    response = c.get('/company/live/data')
    row = response.json()['sessions'][0]
    assert row['latest_frame'] == {'id': '000001', 'timestamp': '2026-11-07T22:00:03Z'}
    assert row['goal'] == '<script>alert(1)</script> Find quota'  # browser renders via textContent
    assert str(tmp_path) not in response.text and 'private-request-secret' not in response.text
    assert 'private-image-token' not in response.text and 'frames/000001.png' not in response.text
    image = c.get('/company/live/frames/cloud/sess_live/000001')
    assert image.status_code == 200 and image.content == PNG
    assert image.headers['content-type'] == 'image/png'
    assert image.headers['cache-control'] == 'no-store'
    assert image.headers['cross-origin-resource-policy'] == 'same-origin'


def test_only_explicit_sources_are_read_and_colliding_ids_remain_separate(tmp_path):
    first, second, excluded = (tmp_path / name for name in ['one', 'two', 'excluded'])
    frame(episode(first, goal='First company'))
    frame(episode(second, goal='Second company'))
    episode(excluded, goal='Must not be discovered')
    c = client({'one': first, 'two': second})
    rows = c.get('/company/live/data?root=' + str(excluded)).json()['sessions']
    assert {(r['source_id'], r['goal']) for r in rows} == {('one', 'First company'), ('two', 'Second company')}
    assert c.get('/company/live/sessions/excluded/sess_live').status_code == 404
    assert c.get('/company/live/sessions/one/sess_live').json()['goal'] == 'First company'


def test_legacy_screenshots_are_not_automatically_published(tmp_path):
    folder = episode(tmp_path, state='resolved')
    (folder / 'before.png').write_bytes(PNG)
    (folder / 'after.png').write_bytes(PNG)
    c = client({'odoo': tmp_path})
    assert c.get('/company/live/data').json()['sessions'][0]['latest_frame'] is None
    assert c.get('/company/live/frames/odoo/sess_live/before').status_code == 404


@pytest.mark.parametrize('policy', ['no_grant', 'frame_login', 'episode_auth', 'quarantine', 'missing_meta'])
def test_frame_publication_requires_explicit_grant_and_non_auth_phase(tmp_path, policy):
    folder = episode(tmp_path, phase='auth' if policy == 'episode_auth' else 'working')
    frame(folder, grant=policy != 'no_grant', phase='login' if policy == 'frame_login' else 'working')
    if policy == 'quarantine':
        (folder / 'quarantine.json').write_text('malformed marker is sufficient')
    if policy == 'missing_meta':
        (folder / 'episode.json').unlink()
    c = client({'cloud': tmp_path})
    assert c.get('/company/live/frames/cloud/sess_live/000001').status_code == 404
    rows = c.get('/company/live/data').json()['sessions']
    assert not rows or rows[0]['latest_frame'] is None
    if policy == 'quarantine':
        assert rows[0]['goal'] == 'Contenu en quarantaine · masqué'
        assert rows[0]['events'] == []


@pytest.mark.parametrize('attack', ['path_traversal', 'absolute_path', 'image_symlink', 'folder_symlink',
                                  'episode_symlink', 'mismatched_hash', 'non_image'])
def test_manifest_cannot_publish_unrelated_or_replaced_files(tmp_path, attack):
    root = tmp_path / 'root'
    folder = episode(root)
    item = frame(folder)
    secret = tmp_path / 'private.png'
    secret.write_bytes(PNG)
    if attack == 'path_traversal':
        item['path'] = '../../private.png'
    elif attack == 'absolute_path':
        item['path'] = str(secret)
    elif attack == 'image_symlink':
        (folder / item['path']).unlink()
        (folder / item['path']).symlink_to(secret)
    elif attack == 'folder_symlink':
        (folder / item['path']).unlink()
        (folder / 'frames').rmdir()
        (folder / 'frames').symlink_to(tmp_path)
    elif attack == 'episode_symlink':
        moved = tmp_path / 'moved-episode'
        folder.rename(moved)
        folder.symlink_to(moved, target_is_directory=True)
    elif attack == 'mismatched_hash':
        item['sha256'] = '0' * 64
    elif attack == 'non_image':
        content = b'<svg onload="alert(1)">Private payload</svg>'
        (folder / item['path']).write_bytes(content)
        item['sha256'] = hashlib.sha256(content).hexdigest()
    if attack != 'episode_symlink':
        write(folder, 'frames.json', {'frames': [item]})
    c = client({'cloud': root})
    assert c.get('/company/live/frames/cloud/sess_live/000001').status_code == 404
    assert c.get('/company/live/frames/cloud/sess_live/..%2Fprivate').status_code == 404


def test_reasoning_raw_tool_arguments_and_signed_links_are_not_in_timeline(tmp_path):
    folder = episode(tmp_path)
    events = [
        {'type': 'reasoning_event', 'message': 'private internal analysis'},
        {'type': 'step', 'message': 'private thought', 'data': {'step': {'kind': 'thought'}}},
        {'type': 'action_event', 'tool_names': ['click'], 'data': {'args': {'password': 'private-password'}}},
        {'type': 'observation_event', 'data': {'image': {'source': 'https://private.invalid/signed'}}},
        {'type': 'message', 'phase': 'auth', 'message': 'hidden auth message'},
        {'type': 'message', 'message': 'https://cdn.invalid/frame?X-Amz-Signature=hide-this hk-' + 'a' * 40},
        {'type': {'invalid': True}, 'message': 'ignore malformed type'},
    ]
    (folder / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events) + '\n{"partial":')
    c = client({'cloud': tmp_path})
    response = c.get('/company/live/sessions/cloud/sess_live')
    assert response.status_code == 200
    for private in ['private internal analysis', 'private thought', 'private-password',
                    'https://private.invalid', 'hidden auth message', 'hide-this', 'a' * 40]:
        assert private not in response.text
    assert 'Action navigateur: click' in response.text
    assert '[lien privé masqué]' in response.text and '[secret masqué]' in response.text


def test_engine_ai_and_human_outcomes_are_not_collapsed(tmp_path):
    folder = episode(tmp_path, state='resolved')
    write(folder, 'report.json', {'declared': {'summary': 'I completed the task'},
                                'verification': {'satisfied': True, 'observed': 'Record visible'}})
    write(folder, 'agent-review.json', {'task_success_agent': 'partial', 'scope_compliance_agent': 'success',
                                      'rationale': ['User answer misses a field']})
    write(folder, 'labels.json', {'task_success_user': 'success', 'useful': 'yes', 'user_confirmed': False})
    c = client({'cloud': tmp_path})
    row = c.get('/company/live/sessions/cloud/sess_live').json()
    assert row['state'] == 'resolved' and row['verified'] is True
    assert row['agent_verdict'] == 'partial' and row['human_verdict'] is None and row['human_useful'] is None
    write(folder, 'labels.json', {'task_success_user': 'failure', 'useful': 'no', 'user_confirmed': True})
    row = c.get('/company/live/sessions/cloud/sess_live').json()
    assert row['human_verdict'] == 'failure' and row['human_useful'] == 'no'


def test_malformed_labels_do_not_break_the_monitor_and_no_mutation_route_exists(tmp_path):
    folder = episode(tmp_path)
    write(folder, 'agent-review.json', {'task_success_agent': {'invalid': True}})
    write(folder, 'labels.json', {'task_success_user': [], 'useful': {}, 'user_confirmed': True})
    c = client({'cloud': tmp_path})
    assert c.get('/company/live/data').status_code == 200
    assert c.get('/company/live/sessions/cloud/sess_live').json()['human_verdict'] is None
    assert c.post('/company/live/data', json={'action': 'run'}).status_code == 405


@pytest.mark.parametrize('flag', [{'scope_violation': True}, {'quarantined': True}, {'phase': 'quarantine'}])
def test_metadata_quarantine_hides_all_payloads_without_marker(tmp_path, flag):
    folder = episode(tmp_path, goal='private goal')
    frame(folder)
    meta = json.loads((folder / 'episode.json').read_text())
    write(folder, 'episode.json', {**meta, **flag})
    write(folder, 'report.json', {'declared': 'private answer'})
    (folder / 'events.jsonl').write_text(json.dumps({'type': 'message', 'message': 'private event'}))
    c = client({'cloud': tmp_path})
    for route in ['/data', '/sessions/cloud/sess_live']:
        response = c.get('/company/live' + route)
        assert response.status_code == 200
        assert all(value not in response.text for value in ['private goal', 'private answer', 'private event'])
    assert c.get('/company/live/frames/cloud/sess_live/000001').status_code == 404


def test_cloud_declared_text_and_sanitized_provider_events_are_visible(tmp_path):
    folder = episode(tmp_path)
    write(folder, 'report.json', {'declared': 'The documented quota is ten concurrent sessions.'})
    events = [
        {'type': 'provider_event', 'provider_kind': 'action_event', 'message': 'Browser actions: click'},
        {'type': 'provider_event', 'provider_kind': 'message_event', 'message': 'Quota located'},
        {'type': 'provider_event', 'provider_kind': 'reasoning_event', 'message': 'hidden reasoning'},
        {'type': 'provider_event', 'provider_kind': 'message_event', 'phase': 'authentication', 'message': 'hidden auth'},
        {'type': 'provider_event', 'provider_kind': 'unknown_private_event', 'message': 'hidden unknown'},
    ]
    (folder / 'events.jsonl').write_text('\n'.join(json.dumps(item) for item in events))
    response = client({'cloud': tmp_path}).get('/company/live/sessions/cloud/sess_live')
    assert response.json()['declared'] == 'The documented quota is ten concurrent sessions.'
    assert [item['message'] for item in response.json()['events']] == ['Browser actions: click', 'Quota located']
    assert 'hidden' not in response.text


def test_answer_then_close_preserves_raw_status_without_claiming_success(tmp_path):
    folder = episode(tmp_path, state='interrupted')
    meta = json.loads((folder / 'episode.json').read_text())
    write(folder, 'episode.json', {**meta, 'provider_status': {'status': 'interrupted', 'private_field': 'hide me'},
        'completion_reason': 'answered_then_cancelled_for_terminal_confirmation'})
    c = client({'cloud': tmp_path})
    row = c.get('/company/live/sessions/cloud/sess_live').json()
    assert row['state'] == row['provider_state'] == 'interrupted'
    assert row['completion_reason'] == 'answered_then_cancelled_for_terminal_confirmation'
    assert row['agent_verdict'] is None and row['human_verdict'] is None and row['verified'] is None
    assert 'hide me' not in json.dumps(row)
    assert 'Réponse reçue · session fermée' in c.get('/company/live').text


@pytest.mark.parametrize('flag', ['authentication_required', 'display_blocked'])
def test_terminal_auth_block_keeps_previous_authorized_frames_hidden(tmp_path, flag):
    folder = episode(tmp_path, state='interrupted', phase='finished')
    frame(folder)  # a formerly permitted frame must not reappear at termination
    meta = json.loads((folder / 'episode.json').read_text())
    write(folder, 'episode.json', {**meta, flag: True,
        'completion_reason': 'answered_then_cancelled_for_terminal_confirmation'})
    write(folder, 'report.json', {'declared': {'summary': 'Access blocked; sign-in is required.'}})
    c = client({'cloud': tmp_path})
    row = c.get('/company/live/sessions/cloud/sess_live').json()
    assert row[flag] is True and row['latest_frame'] is None and row['frames'] == []
    assert row['state'] == 'interrupted' and row['declared'] == 'Access blocked; sign-in is required.'
    assert row['quarantined'] is False  # retain the useful blocked-access explanation
    assert c.get('/company/live/data').json()['sessions'][0]['latest_frame'] is None
    assert c.get('/company/live/frames/cloud/sess_live/000001').status_code == 404
    assert 'Connexion requise' in c.get('/company/live').text
