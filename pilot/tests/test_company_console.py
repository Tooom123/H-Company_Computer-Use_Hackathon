"""Company console tests; no model, browser, microphone or live pilot involved."""
import hashlib
import json
import re
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from pilot.company_console import COOKIE, MAX_DOCUMENT_BYTES, mount_company_console


PASSWORD = 'offline-company-secret-not-a-credential'


class KnowledgeFake:
    def __init__(self):
        self.uploaded = []

    def upload(self, filename, content):
        self.uploaded.append((filename, content))

    def list_documents(self):
        return [{'filename': filename, 'document_id': 'guide', 'sha256': hashlib.sha256(content).hexdigest()}
                for filename, content in self.uploaded]

    def search(self, query, top_k=4):
        return [{'document_id': 'guide', 'sha256': 'abc123', 'section': 'Réceptions',
                 'text': 'La réception partielle crée un reliquat. <script>unsafe()</script>',
                 'citation_uri': 'knowledge://odoo/guide/abc123#chunk-0',
                 'source_urls': ['https://www.odoo.com/documentation/19.0/',
                                 'javascript:alert(1)', 'https://user:secret@example.com', 'https://[bad']}]


def factory(tmp_path, *, knowledge=None, store=None, busy=False, mutation_lock=None, simulated=False):
    app = FastAPI()
    knowledge = knowledge or KnowledgeFake()
    mount_company_console(app, private_root=tmp_path, knowledge=knowledge,
                          username='support', password=PASSWORD,
                          config={'software': 'odoo', 'company': '<Demo>',
                                  'domains': ['https://demo.invalid'],
                                  'api_key': 'never-render-this-secret', 'simulated': simulated},
                          store=store, is_busy=lambda: busy, mutation_lock=mutation_lock)
    client = TestClient(app, base_url='http://127.0.0.1:8777')
    client.auth = ('support', PASSWORD)
    return client, knowledge


def csrf(client):
    result = client.get('/company/documents')
    assert result.status_code == 200
    return re.search(r'name="csrf" value="([^"]+)"', result.text)[1]


def episode(root, sid, *, state='resolved', quarantined=False, simulated=False,
            human=None, review=None, goal='Find the product'):
    directory = root / 'episodes' / sid
    directory.mkdir(parents=True)
    (directory / 'episode.json').write_text(json.dumps({'scenario_id': 'R01', 'state': state,
                                                       'simulated': simulated, 'export_status': 'complete'}))
    (directory / 'report.json').write_text(json.dumps({'goal': goal, 'simulated': simulated,
        'declared': {'summary': 'Agent declared done'},
        'verification': {'observed': 'Verifier observed the record', 'satisfied': True,
                         'evidence_refs': ['private-reference-must-not-be-rendered']},
        'evidence': [{'path': '/private/location/screenshot.png'}]}))
    if human is not None:
        (directory / 'labels.json').write_text(json.dumps(human))
    if review is not None:
        (directory / 'agent-review.json').write_text(json.dumps(review))
    if quarantined:
        (directory / 'quarantine.json').write_text(json.dumps({'status': 'quarantined', 'reason': 'private-reason'}))
    return directory


@pytest.mark.parametrize('path', ['/company', '/company/', '/company/documents', '/company/sessions', '/company/sessions/sess_missing'])
def test_every_route_requires_basic_auth(tmp_path, path):
    client, _ = factory(tmp_path)
    assert client.get(path, auth=None).status_code == 401
    assert client.get(path, auth=('support', 'wrong')).status_code == 401
    assert client.get(path, auth=None, headers={'Authorization': 'Bearer ' + PASSWORD}).status_code == 401
    assert client.get(path + '?token=' + PASSWORD, auth=None).status_code == 401


def test_cloud_string_declared_report_is_compatible(tmp_path):
    folder = episode(tmp_path, 'sess_cloud')
    (folder / 'report.json').write_text(json.dumps({'declared': 'Cloud final answer', 'verification': None}))
    client, _ = factory(tmp_path)
    response = client.get('/company/sessions/sess_cloud')
    assert response.status_code == 200 and 'Cloud final answer' in response.text


@pytest.mark.parametrize('flag', [{'scope_violation': True}, {'quarantined': True}, {'phase': 'quarantine'}])
def test_cloud_quarantine_metadata_hides_all_content(tmp_path, flag):
    folder = episode(tmp_path, 'sess_cloud', goal='PRIVATE GOAL')
    meta = json.loads((folder / 'episode.json').read_text())
    (folder / 'episode.json').write_text(json.dumps({**meta, **flag}))
    client, _ = factory(tmp_path)
    response = client.get('/company/sessions/sess_cloud')
    assert response.status_code == 200 and 'Contenu privé masqué' in response.text
    assert 'PRIVATE GOAL' not in response.text and 'Agent declared done' not in response.text


def test_config_has_no_credentials_or_injected_markup(tmp_path):
    client, _ = factory(tmp_path)
    response = client.get('/company')
    assert response.status_code == 200
    assert '&lt;Demo&gt;' in response.text
    assert PASSWORD not in response.text and 'never-render-this-secret' not in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['referrer-policy'] == 'same-origin'
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert client.get('/company', headers={'Host': 'attacker.invalid'}).status_code == 403
    assert client.get('/company', headers={'Host': '[broken'}).status_code == 403
    assert client.get('/company', headers={'Origin': 'https://attacker.invalid'}).status_code == 403


def test_upload_auth_csrf_and_same_origin(tmp_path):
    client, knowledge = factory(tmp_path)
    token = csrf(client)
    files = {'document': ('guide.md', b'# Guide\nRead only', 'text/markdown')}
    assert client.post('/company/documents', files=files, data={'csrf': token}, auth=None).status_code == 401
    assert client.post('/company/documents', files=files).status_code == 403
    assert client.post('/company/documents', files=files, data={'csrf': 'wrong'}).status_code == 403
    assert client.post('/company/documents', files=files, data={'csrf': token},
                       headers={'Origin': 'https://attacker.invalid'}).status_code == 403
    result = client.post('/company/documents', files=files, data={'csrf': token},
                         headers={'Origin': 'http://127.0.0.1:8777'}, follow_redirects=False)
    assert result.status_code == 303
    assert knowledge.uploaded == [('guide.md', b'# Guide\nRead only')]
    assert 'guide.md' in client.get('/company/documents').text


@pytest.mark.parametrize('filename', ['../outside.md', '..\\outside.md', '/tmp/outside.md', 'not-markdown.html', 'nul\x00.md'])
def test_upload_rejects_traversal_and_invalid_filename(tmp_path, filename):
    client, knowledge = factory(tmp_path)
    result = client.post('/company/documents', data={'csrf': csrf(client)},
                         files={'document': (filename, b'# Document', 'text/markdown')})
    assert result.status_code == 422
    assert not knowledge.uploaded


def test_upload_limits_utf8_and_busy_guard(tmp_path):
    client, knowledge = factory(tmp_path)
    token = csrf(client)
    for content, status in [(b'\xff', 422), (b'x' * (MAX_DOCUMENT_BYTES + 1), 413),
                            (b'x' * (MAX_DOCUMENT_BYTES + 20000), 413)]:
        response = client.post('/company/documents', data={'csrf': token}, files={'document': ('guide.md', content)})
        assert response.status_code == status
    assert not knowledge.uploaded
    busy_client, busy_knowledge = factory(tmp_path, busy=True)
    assert busy_client.post('/company/documents', data={'csrf': csrf(busy_client)},
                            files={'document': ('guide.md', b'# Document')}).status_code == 409
    assert not busy_knowledge.uploaded


def test_search_preserves_actual_citation_and_escapes_source(tmp_path):
    client, _ = factory(tmp_path)
    result = client.post('/company/documents/search', data={'csrf': csrf(client), 'query': 'Comment réceptionner partiellement ?'})
    assert result.status_code == 200
    assert 'knowledge://odoo/guide/abc123#chunk-0' in result.text
    assert 'https://www.odoo.com/documentation/19.0/' in result.text
    assert 'abc123' in result.text and 'La réception partielle crée un reliquat.' in result.text
    assert '<details><summary>Version et provenance</summary>' in result.text
    assert '<details open' not in result.text
    assert '<p class="muted">guide</p>' in result.text
    assert '<script>' not in result.text and '&lt;script&gt;' in result.text
    assert 'javascript:alert' not in result.text and 'user:secret' not in result.text
    assert client.post('/company/documents/search', data={'query': 'Question'}).status_code == 403


def test_quarantine_excluded_from_kpis_and_no_sensitive_content(tmp_path):
    episode(tmp_path, 'sess_real', human={'user_confirmed': True, 'task_success_user': 'partial', 'useful': 'yes'},
            review={'task_success_agent': 'success', 'scope_compliance_agent': 'unknown'})
    episode(tmp_path, 'sess_quarantine', quarantined=True, goal='secret-quarantined-goal',
            human={'user_confirmed': True, 'task_success_user': 'success', 'useful': 'yes'},
            review={'task_success_agent': 'success'})
    episode(tmp_path, 'sess_simulated', simulated=True, human={'user_confirmed': True}, review={'task_success_agent': 'success'})
    episode(tmp_path, 'sess_running', state='running', human={'user_confirmed': True}, review={'task_success_agent': 'success'})
    client, _ = factory(tmp_path)
    listing = client.get('/company/sessions').text
    for metric in ['Sessions réelles terminées retenues', 'Retours humains confirmés', 'Revues IA disponibles', 'Sessions en quarantaine']:
        assert f'<span>{metric}</span><strong>1</strong>' in listing
    assert 'secret-quarantined-goal' not in listing
    detail = client.get('/company/sessions/sess_quarantine').text
    assert 'Contenu privé masqué' in detail and 'secret-quarantined-goal' not in detail
    assert 'private-reason' not in detail


def test_labels_stay_distinct_and_no_human_label_is_inferred(tmp_path):
    episode(tmp_path, 'sess_one', human={'user_confirmed': True, 'task_success_user': 'partial', 'useful': 'no', 'comment': 'Pas utile'},
            review={'task_success_agent': 'success', 'scope_compliance_agent': 'unknown', 'rationale': 'Le résultat est visible.'})
    episode(tmp_path, 'sess_two', review={'task_success_agent': 'success'})
    client, _ = factory(tmp_path)
    detail = client.get('/company/sessions/sess_one').text
    assert 'Réussite : Partiel · Utilité : Non' in detail
    assert 'Réussite : Réussi · Périmètre : Non évalué' in detail
    assert 'Pas utile' in detail
    assert '/private/location' not in detail and 'private-reference' not in detail
    missing = client.get('/company/sessions/sess_two').text
    assert 'Réussite : Non recueilli · Utilité : Non recueillie' in missing
    assert not (tmp_path / 'episodes/sess_two/labels.json').exists()


def test_episode_symlinks_and_path_traversal_never_read_external_files(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'episode.json').write_text('{"state":"resolved","title":"private-outside-secret"}')
    base = tmp_path / 'episodes'
    base.mkdir()
    (base / 'sess_link').symlink_to(outside, target_is_directory=True)
    directory = base / 'sess_filelink'
    directory.mkdir()
    (directory / 'episode.json').symlink_to(outside / 'episode.json')
    client, _ = factory(tmp_path)
    assert 'private-outside-secret' not in client.get('/company/sessions').text
    for path in ['sess_link', 'sess_filelink', '..%2Foutside']:
        assert client.get('/company/sessions/' + path).status_code == 404


def test_quarantine_store_rows_not_grouped(tmp_path, monkeypatch):
    episode(tmp_path, 'sess_visible')
    episode(tmp_path, 'sess_hidden', quarantined=True)
    seen = []
    def groups(cases):
        seen.extend(case.session_id for case in cases)
        return []
    import hcs_backend.grouping
    monkeypatch.setattr(hcs_backend.grouping, 'group_cases', groups)
    store = SimpleNamespace(list_cases=lambda: [SimpleNamespace(session_id=sid, simulated=False, demo_data=False)
                           for sid in ['sess_visible', 'sess_hidden', 'sess_unlinked']])
    client, _ = factory(tmp_path, store=store)
    assert client.get('/company/sessions').status_code == 200
    assert seen == ['sess_visible']


def test_signed_csrf_cannot_be_forged_by_matching_cookie_and_form(tmp_path):
    client, knowledge = factory(tmp_path)
    fake = '9999999999.' + 'a' * 32 + '.' + 'b' * 64
    client.cookies.set(COOKIE, fake, path='/company')
    result = client.post('/company/documents', data={'csrf': fake}, files={'document': ('guide.md', b'# Guide')})
    assert result.status_code == 403 and not knowledge.uploaded


def test_shared_mutation_lock_covers_busy_check_and_upload(tmp_path):
    class LockSpy:
        held = False
        def __enter__(self):
            self.held = True
        def __exit__(self, *args):
            self.held = False
    lock = LockSpy()
    class KnowledgeLocked(KnowledgeFake):
        def upload(self, filename, content):
            assert lock.held
            super().upload(filename, content)
    client, knowledge = factory(tmp_path, knowledge=KnowledgeLocked(), mutation_lock=lock)
    result = client.post('/company/documents', data={'csrf': csrf(client)},
                         files={'document': ('guide.md', b'# Guide')}, follow_redirects=False)
    assert result.status_code == 303 and knowledge.uploaded
    assert not lock.held


def test_simulated_console_is_labelled_on_all_screens(tmp_path):
    client, _ = factory(tmp_path, simulated=True)
    for path in ['/company', '/company/documents', '/company/sessions']:
        assert 'Mode simulé · aucun résultat réel de Holo' in client.get(path).text


def test_document_versions_are_short_with_full_hash_available(tmp_path):
    knowledge = KnowledgeFake()
    content = b'# Read-only guide'
    knowledge.upload('guide.md', content)
    client, _ = factory(tmp_path, knowledge=knowledge)
    result = client.get('/company/documents').text
    digest = hashlib.sha256(content).hexdigest()
    assert f'<code title="{digest}">{digest[:12]}</code>' in result
    assert 'guide.md' in result


@pytest.mark.parametrize('state', ['stopped', 'preflight_failed'])
def test_terminal_failed_or_stopped_runs_remain_in_denominators(tmp_path, state):
    episode(tmp_path, 'sess_terminal', state=state,
            human={'user_confirmed': True, 'task_success_user': 'failed', 'useful': 'no'},
            review={'task_success_agent': 'failure'})
    client, _ = factory(tmp_path)
    listing = client.get('/company/sessions').text
    for metric in ['Sessions réelles terminées retenues', 'Retours humains confirmés', 'Revues IA disponibles']:
        assert f'<span>{metric}</span><strong>1</strong>' in listing
    assert f'<td>{state}</td>' in listing


def test_review_rationale_is_escaped_collapsed_list_and_labels_unchanged(tmp_path):
    directory = episode(tmp_path, 'sess_review',
        human={'user_confirmed': True, 'task_success_user': 'failed', 'useful': 'unknown'},
        review={'task_success_agent': 'partial', 'scope_compliance_agent': 'failure',
                'rationale': ['First observation.', '<script>unsafe()</script>']})
    before = (directory / 'agent-review.json').read_bytes()
    client, _ = factory(tmp_path)
    detail = client.get('/company/sessions/sess_review').text
    assert 'Réussite : Échec · Utilité : Non évalué' in detail
    assert 'Réussite : Partiel · Périmètre : Échec' in detail
    assert '<details><summary>Lire l’analyse IA (2 point(s))</summary><ul>' in detail
    assert '<li>First observation.</li>' in detail
    assert '<li>&lt;script&gt;unsafe()&lt;/script&gt;</li>' in detail
    assert '<script>' not in detail and '<details open' not in detail
    assert (directory / 'agent-review.json').read_bytes() == before
    assert json.loads((directory / 'labels.json').read_text())['task_success_user'] == 'failed'
