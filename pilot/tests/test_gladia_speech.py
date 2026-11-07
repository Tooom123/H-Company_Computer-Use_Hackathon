"""Gladia protocol tests with MockTransport; no credentials/network/audio service."""
import asyncio
import json
import time

import httpx
import pytest

from pilot.gladia_speech import GladiaSpeech, GladiaSpeechError


JOB = '45463597-20b7-4af7-b3b3-f5fb778203ab'
UPLOAD = 'https://api.gladia.io/file/636c70f6-92c1-4026-a8b6-0dfe3ecf826f'
FAKE_KEY = 'test-key-never-valid'


def recording(tmp_path):
    path = tmp_path/'private-original-name.wav'
    path.write_bytes(b'only-offline-transport-fixture')
    return path


def prepared_job(request):
    if request.url.path == '/v2/upload':
        return httpx.Response(200, json={'audio_url': UPLOAD})
    if request.url.path == '/v2/pre-recorded':
        return httpx.Response(200, json={'id': JOB, 'result_url': 'https://attacker.invalid/steal'})
    return None


def test_upload_once_submit_once_poll_fixed_host_and_extract_only_transcript(tmp_path, caplog):
    requests = []
    states = iter(['queued', 'processing', 'done'])

    def handler(request):
        requests.append(request)
        assert request.url.scheme == 'https' and request.url.host == 'api.gladia.io'
        assert request.headers['x-gladia-key'] == FAKE_KEY
        if request.url.path == '/v2/upload':
            assert b'filename="recording.wav"' in request.content
            assert b'private-original-name' not in request.content
        if request.url.path == '/v2/pre-recorded':
            body = json.loads(request.content)
            assert body['model'] == 'solaria-3'
            assert body['language_config'] == {'languages': ['fr'], 'code_switching': False}
            assert body['audio_url'] == UPLOAD
            assert 'custom_vocabulary' not in body
        setup = prepared_job(request)
        if setup is not None:
            return setup
        assert request.url.path == '/v2/pre-recorded/' + JOB
        return httpx.Response(200, json={'status': next(states), 'result': {
            'transcription': {'full_transcript': '  Retrouve le gingembre.  '},
            'extra_sensitive': 'must not be returned',
        }})

    speech = GladiaSpeech(FAKE_KEY, transport=httpx.MockTransport(handler), poll_interval_s=0)
    assert speech.ready is True
    assert speech(recording(tmp_path), 'audio/wav') == {
        'transcript': 'Retrouve le gingembre.', 'provider': 'Gladia'}
    assert [r.method for r in requests] == ['POST', 'POST', 'GET', 'GET', 'GET']
    assert FAKE_KEY not in caplog.text
    assert 'Retrouve le gingembre' not in caplog.text


@pytest.mark.parametrize('status,expected', [(401, 'Clé'), (403, 'Clé'), (429, 'quota'),
                                           (503, 'indisponible'), (400, 'refusé')])
def test_safe_http_failures_never_include_provider_body_or_key(tmp_path, status, expected):
    def handler(request):
        return httpx.Response(status, json={'message': 'private audio and ' + FAKE_KEY})

    speech = GladiaSpeech(FAKE_KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(GladiaSpeechError, match=expected) as exc:
        speech(recording(tmp_path), 'audio/wav')
    assert FAKE_KEY not in str(exc.value)
    assert 'private audio' not in str(exc.value)
    assert speech.message == str(exc.value)


def test_redirect_is_not_followed_and_never_forwards_key(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(307, headers={'Location': 'https://attacker.invalid/steal'})

    speech = GladiaSpeech(FAKE_KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(GladiaSpeechError):
        speech(recording(tmp_path), 'audio/wav')
    assert len(requests) == 1
    assert requests[0].url.host == 'api.gladia.io'


@pytest.mark.parametrize('upload_url', [
    'http://api.gladia.io/file/id', 'https://api.gladia.io.attacker.invalid/file/id',
    'https://api.gladia.io@attacker.invalid/file/id', 'https://api.gladia.io:444/file/id',
    'https://api.gladia.io/v2/upload', 'https://user:pass@api.gladia.io/file/id',
])
def test_unexpected_upload_urls_are_not_submitted(tmp_path, upload_url):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'audio_url': upload_url})

    speech = GladiaSpeech(FAKE_KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(GladiaSpeechError, match='adresse'):
        speech(recording(tmp_path), 'audio/wav')
    assert len(requests) == 1


@pytest.mark.parametrize('final', [
    {'status': 'error', 'error': 'sensitive provider message'},
    {'status': 'done', 'result': {'transcription': {'full_transcript': ''}}},
    {'status': 'done', 'result': None},
    {'status': 'unexpected'},
])
def test_job_errors_empty_transcripts_and_unknown_states_fail_without_inventing_text(tmp_path, final):
    def handler(request):
        setup = prepared_job(request)
        return setup if setup is not None else httpx.Response(200, json=final)

    speech = GladiaSpeech(FAKE_KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(GladiaSpeechError) as exc:
        speech(recording(tmp_path), 'audio/wav')
    assert 'sensitive' not in str(exc.value)


def test_total_timeout_cancels_inflight_request_without_reposting(tmp_path):
    calls = []

    async def handler(request):
        calls.append(request.url.path)
        await asyncio.sleep(1)
        return httpx.Response(200, json={'audio_url': UPLOAD})

    speech = GladiaSpeech(FAKE_KEY, transport=httpx.MockTransport(handler), timeout_s=.03)
    start = time.monotonic()
    with pytest.raises(GladiaSpeechError, match='délai'):
        speech(recording(tmp_path), 'audio/wav')
    assert time.monotonic() - start < .5
    assert calls == ['/v2/upload']


def test_total_timeout_applies_across_polling_not_individual_requests(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        setup = prepared_job(request)
        return setup if setup is not None else httpx.Response(200, json={'status': 'processing'})

    speech = GladiaSpeech(FAKE_KEY, transport=httpx.MockTransport(handler), timeout_s=.05,
                          poll_interval_s=.01)
    with pytest.raises(GladiaSpeechError, match='délai'):
        speech(recording(tmp_path), 'audio/wav')
    assert calls.count('/v2/upload') == 1
    assert calls.count('/v2/pre-recorded') == 1
    assert calls.count('/v2/pre-recorded/' + JOB) > 1


def test_no_key_unsupported_type_or_missing_file_never_call_transport(tmp_path):
    calls = []
    speech = GladiaSpeech('', transport=httpx.MockTransport(lambda r: calls.append(r)))
    assert not speech.ready
    with pytest.raises(GladiaSpeechError, match='absente'):
        speech(recording(tmp_path), 'audio/wav')
    speech = GladiaSpeech(FAKE_KEY, transport=httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(GladiaSpeechError, match='WAV'):
        speech(recording(tmp_path), 'text/plain')
    with pytest.raises(GladiaSpeechError, match='absent'):
        speech(tmp_path/'missing.wav', 'audio/wav')
    assert not calls


def test_deadline_cannot_exceed_ipc_budget():
    for timeout in (0, -1, 111, float('inf'), float('nan')):
        with pytest.raises(ValueError):
            GladiaSpeech(FAKE_KEY, timeout_s=timeout)
