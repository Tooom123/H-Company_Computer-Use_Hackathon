"""Offline checks across the launcher/auth/episode boundary; never uses a browser."""
import json

import pytest
from fastapi.testclient import TestClient
from hcs_agent.backend import MockBackend

from pilot.runtime_config import browser_credentials
from pilot.server import create_app

ORIGIN = 'https://holo-demo.62.83.79.254.sslip.io'
TOKEN = 'test-browser-worker-private-token'
AUTH = {'Authorization': 'Bearer ' + TOKEN}


def test_private_logins_are_scoped_and_errors_do_not_disclose_values(tmp_path):
    public = {'url': ORIGIN + '/web/login', 'login': 'basic-user', 'password': 'fake-basic-secret'}
    (tmp_path / 'public-access.json').write_text(json.dumps(public))
    (tmp_path / 'demo-access.json').write_text(json.dumps({'login': 'odoo-user', 'password': 'fake-odoo-secret'}))
    assert browser_credentials(tmp_path, expected_origin=ORIGIN)['odoo_username'] == 'odoo-user'
    public['url'] = 'https://fake-basic-secret@attacker.invalid/web/login'
    (tmp_path / 'public-access.json').write_text(json.dumps(public))
    with pytest.raises(ValueError) as error:
        browser_credentials(tmp_path, expected_origin=ORIGIN)
    assert 'fake-basic-secret' not in str(error.value)
    assert 'attacker' not in str(error.value)


def test_browser_episode_retains_observation_and_document_revision(tmp_path):
    from pilot.knowledge import LocalMarkdownKnowledge
    knowledge = LocalMarkdownKnowledge(tmp_path / 'docs')
    knowledge.upload('guide.md', '# Achats\nUne réception partielle conserve un reliquat.')
    app = create_app(private_root=tmp_path / 'worker', token=TOKEN, backend=MockBackend(step_delay_s=0),
                     environment='rich', transport='browser', viewport={'width': 1280, 'height': 832},
                     knowledge=knowledge, knowledge_enabled=True,
                     engine_revision='0ffda3f', support_revision='e46f9ee')
    with TestClient(app) as client:
        response = client.post('/pilot/episodes', headers=AUTH, json={'scenario_id': 'R03', 'goal': 'Lire la commande.'})
        assert response.status_code == 201
        episode = response.json()
        assert episode['pilot']['image_policy'] == 'browser_viewport'
        assert episode['pilot']['viewport'] == {'width': 1280, 'height': 832}
        assert episode['pilot']['knowledge'] == {'enabled': True, **knowledge.fingerprint()}
        request = json.loads((tmp_path / 'worker/episodes' / episode['session_id'] / 'request.json').read_text())
        assert request['transport'] == 'browser'
        assert request['knowledge'] == episode['pilot']['knowledge']
        assert client.get('/company').status_code == 401


def test_transport_cannot_relabel_old_desktop_episodes(tmp_path):
    create_app(private_root=tmp_path, token=TOKEN, backend=MockBackend())
    with pytest.raises(ValueError, match='separate private directory'):
        create_app(private_root=tmp_path, token=TOKEN, backend=MockBackend(), transport='browser')


def test_company_auth_exemption_does_not_expose_engine_routes(tmp_path):
    from pilot.knowledge import LocalMarkdownKnowledge
    knowledge = LocalMarkdownKnowledge(tmp_path / 'docs')
    app = create_app(private_root=tmp_path / 'worker', token=TOKEN, backend=MockBackend(),
                     knowledge=knowledge, console_credentials=('support', 'fake-console-password'))
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/company').status_code == 401
        assert client.get('/company', auth=('support', 'fake-console-password'),
                          headers={'Host': '127.0.0.1'}).status_code == 200
        assert client.get('/company-unprotected', auth=('support', 'fake-console-password')).status_code == 401
        assert client.get('/pilot/status', auth=('support', 'fake-console-password')).status_code == 401
        assert client.get('/pilot/status', headers={**AUTH, 'Origin': 'https://example.invalid'}).status_code == 401
