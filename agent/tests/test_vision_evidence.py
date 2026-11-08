import base64
import hashlib
import io
import json

import httpx
from PIL import Image
import pytest

from hcs_agent import grounding, vision_evidence as ve


@pytest.mark.parametrize('fails', [False, True])
def test_trace_matches_http_image_and_distinguishes_response_from_error(tmp_path, monkeypatch, fails):
    data = io.BytesIO()
    Image.new('RGB', (80, 50), 'red').save(data, format='JPEG')
    raw = data.getvalue()
    encoded = base64.b64encode(raw).decode()
    monkeypatch.setattr(ve, 'RECORDER', ve.Recorder(tmp_path, lambda: {'session_id': 'sess_test'}))
    sent = []
    def request(req):
        sent.append(json.loads(req.content)['messages'][0]['content'][0]['image_url']['url'])
        if fails:
            return httpx.Response(500, json={'error': 'test'})
        return httpx.Response(200, json={'id': 'request-test', 'usage': {'prompt_tokens': 123},
            'choices': [{'message': {'tool_calls': [{'function': {'name': 'locate', 'arguments': '{}'}}]}}]})
    g = grounding.Grounder.__new__(grounding.Grounder)
    g.model = 'test-model'
    g._http = httpx.Client(transport=httpx.MockTransport(request))
    with ve.geometry(kind='crop', region=[10, 10, 80, 50], screen=[200, 100]):
        if fails:
            with pytest.raises(httpx.HTTPStatusError):
                g._call(encoded, 'test', [])
        else:
            g._call(encoded, 'test', [])
    record = json.loads(next(tmp_path.glob('*.json')).read_text())
    image = next(tmp_path.glob('*.jpg'))
    assert image.read_bytes() == base64.b64decode(sent[0].split(',', 1)[1]) == raw
    assert record['sha256'] == hashlib.sha256(raw).hexdigest()
    assert record['session_id'] == 'sess_test'
    assert record['status'] == ('error' if fails else 'completed')
    assert record['usage'] == (None if fails else {'prompt_tokens': 123})
    assert record['latency_ms'] is not None
    assert image.stat().st_mode & 0o777 == 0o600
    assert ve.GEOMETRY.get() is None


def test_recording_off_by_default(monkeypatch):
    monkeypatch.setattr(ve, 'RECORDER', None)
    assert ve.begin('not-an-image', 'model') is None
