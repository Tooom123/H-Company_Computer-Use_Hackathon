"""A richer demo must not inherit the initial lab's episodes or approvals."""
import json

import pytest
from fastapi.testclient import TestClient

from hcs_agent.backend import MockBackend
from pilot.server import create_app

TOKEN = 'offline-environment-test-token'
AUTH = {'Authorization': 'Bearer ' + TOKEN}


def make(root, environment):
    return create_app(private_root=root, token=TOKEN,
                      backend=MockBackend(step_delay_s=0), environment=environment,
                      engine_revision='test-engine', support_revision='test-support')


def test_environment_directory_cannot_be_reused_between_demos(tmp_path):
    with TestClient(make(tmp_path, 'minimal')) as client:
        assert client.get('/pilot/status', headers=AUTH).json()['environment']['id'] == 'odoo-minimal-v1'
    with pytest.raises(ValueError, match='another demo'):
        make(tmp_path, 'rich')


def test_rich_rejects_legacy_untagged_episode_directory(tmp_path):
    old = tmp_path / 'episodes/old'
    old.mkdir(parents=True)
    (old / 'episode.json').write_text('{}')
    with pytest.raises(ValueError, match='untagged episodes'):
        make(tmp_path, 'rich')
    assert not (tmp_path / 'environment.json').exists()


def test_rich_catalog_plan_and_archive_input_keep_identity(tmp_path):
    with TestClient(make(tmp_path, 'rich')) as client:
        status = client.get('/pilot/status', headers=AUTH).json()
        assert status['environment']['entry_url'] == 'http://holo-rich.localhost:18091/odoo/crm'
        assert status['engine_revision'] == 'test-engine'
        cards = client.get('/pilot/scenarios', headers=AUTH).json()
        assert [c['id'] for c in cards] == [f'R{i:02d}' for i in range(1, 11)]
        assert not any(c['requires_reference'] for c in cards)
        assert client.post('/pilot/episodes', headers=AUTH,
                           json={'scenario_id': '01', 'goal': 'ancienne demande'}).status_code == 422
        response = client.post('/pilot/episodes', headers=AUTH,
                               json={'scenario_id': 'R01', 'goal': cards[0]['prompt']})
        assert response.status_code == 201
        made = response.json()
        assert made['state'] == 'awaiting_approval'
        assert made['steps'] == []
        assert made['pilot']['environment']['id'] == 'odoo-rich-v2.1'
        saved = json.loads((tmp_path / 'episodes' / made['session_id'] / 'request.json').read_text())
        assert saved['environment'] == status['environment']
        assert saved['engine_revision'] == 'test-engine'
        assert saved['support_revision'] == 'test-support'
        assert 'HACKATHON — Boutique Démo' not in json.dumps(made['plan'], ensure_ascii=False)
