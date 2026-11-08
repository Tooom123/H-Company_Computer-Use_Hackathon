import json

from fastapi.testclient import TestClient

from hcs_backend.app import create_app
from hcs_backend.config import Settings
from hcs_backend.store import Store


def test_live_view_is_authenticated_and_serves_only_owned_payloads(tmp_path):
    identifier = 'a' * 32
    (tmp_path / (identifier + '.json')).write_text(json.dumps({'id': identifier, 'status': 'completed'}))
    (tmp_path / (identifier + '.jpg')).write_bytes(b'exact-payload')
    other = 'b' * 32
    (tmp_path / (other + '.jpg')).symlink_to(tmp_path / (identifier + '.json'))
    app = create_app(Settings(ingest_token='test', dashboard_password='pw', vision_evidence_dir=tmp_path), Store(':memory:'), start_poller=False)
    app.state.live_status = lambda: {'current': {'session_id': 'sess_test', 'goal': 'My question'}}
    client = TestClient(app)
    for url in ['/dashboard/live', '/dashboard/live/data', '/dashboard/live/frames/' + identifier + '.jpg']:
        assert client.get(url).status_code == 401
        assert client.get(url, auth=('support', 'wrong')).status_code == 401
        assert client.get(url, auth=('support', 'pw')).status_code == 200
    data = client.get('/dashboard/live/data', auth=('support', 'pw')).json()
    assert data['current']['session_id'] == 'sess_test'
    assert len(data['frames']) == 1
    image = client.get('/dashboard/live/frames/' + identifier + '.jpg', auth=('support', 'pw'))
    assert image.content == b'exact-payload' and image.headers['cache-control'] == 'no-store'
    assert client.get('/dashboard/live/frames/' + other + '.jpg', auth=('support', 'pw')).status_code == 404
    assert client.get('/dashboard/live/frames/not-allowed.jpg', auth=('support', 'pw')).status_code == 404
