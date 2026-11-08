import base64
import json
import queue
import threading
import time

import httpx
import pytest

from hcs_agent import voxtral


class Socket:
    def __init__(self, *, final=True, error=False, wrong_format=False):
        self.incoming = queue.Queue()
        self.incoming.put({"type": "session.created", "session": {}})
        self.sent = []
        self.closed = False
        self.final, self.error, self.wrong_format = final, error, wrong_format

    def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        if event["type"] == "session.update":
            settings = event["session"]
            if self.wrong_format:
                settings = {**settings, "audio_format": {"encoding": "pcm_s16le", "sample_rate": 24000}}
            self.incoming.put({"type": "session.updated", "session": settings})
        elif event["type"] == "input_audio.append":
            if self.error:
                self.incoming.put({"type": "error", "error": {"message": "secret-api-key"}})
            else:
                self.incoming.put({"type": "transcription.text.delta", "text": "Hello"})
                self.incoming.put({"type": "transcription.text.delta", "text": " Holo."})
        elif event["type"] == "input_audio.end" and self.final:
            self.incoming.put({"type": "transcription.done", "text": "Hello Holo!"})

    def recv(self, timeout=None):
        try:
            value = self.incoming.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError from None
        if value is None:
            raise ConnectionError("closed")
        return json.dumps(value)

    def close(self):
        self.closed = True
        self.incoming.put(None)


def install(monkeypatch, socket):
    calls = []
    def connect(url, **kwargs):
        calls.append((url, kwargs))
        return socket
    monkeypatch.setattr(voxtral, 'connect', connect)
    return calls


def test_realtime_buffers_audio_then_configures_streams_and_returns_final(monkeypatch):
    socket = Socket()
    calls = install(monkeypatch, socket)
    live = voxtral.VoxtralLiveTranscriber('secret-api-key', language='fr-en')
    partials = []
    live.on_partial = partials.append
    pcm = b'\x01\x02' * 1600
    live.open(['Holo', 'Holo', 'H Company'])
    live.feed(pcm)
    assert live.finish(1) == 'Hello Holo!'
    live._thread.join(1)
    assert not live._thread.is_alive()
    assert socket.closed
    assert calls[0][0].startswith(voxtral.REALTIME_URL)
    assert calls[0][1]['additional_headers']['Authorization'] == 'Bearer secret-api-key'
    assert [e['type'] for e in socket.sent] == ['session.update', 'input_audio.append', 'input_audio.end']
    settings = socket.sent[0]['session']
    assert settings['audio_format'] == {'encoding': 'pcm_s16le', 'sample_rate': 16000}
    assert settings['target_streaming_delay_ms'] == 480
    assert settings['context_bias'] == ['Holo', 'H Company']
    assert 'language' not in settings
    assert base64.b64decode(socket.sent[1]['audio']) == pcm
    assert partials == ['Hello', 'Hello Holo.']


@pytest.mark.parametrize('options', [{'final': False}, {'error': True}, {'wrong_format': True}])
def test_partial_error_or_wrong_format_is_not_accepted_as_final(monkeypatch, options):
    socket = Socket(**options)
    install(monkeypatch, socket)
    live = voxtral.VoxtralLiveTranscriber('secret-api-key')
    live.open()
    live.feed(b'\0\0')
    assert live.finish(.15) is None
    live._thread.join(1)
    assert not live._thread.is_alive()
    assert socket.closed
    assert 'secret-api-key' not in str(live._failed)


def test_cancel_during_connection_does_not_send_audio_or_config(monkeypatch):
    socket = Socket()
    gate = threading.Event()
    started = threading.Event()
    def connect(*args, **kwargs):
        started.set()
        gate.wait(1)
        return socket
    monkeypatch.setattr(voxtral, 'connect', connect)
    live = voxtral.VoxtralLiveTranscriber('test')
    live.open()
    live.feed(b'\0\0')
    assert started.wait(1)
    live.cancel()
    gate.set()
    live._thread.join(1)
    assert not live._thread.is_alive()
    assert live.finish(.01) is None
    assert socket.closed and not socket.sent


def test_explicit_language_is_pinned_and_reopen_is_rejected(monkeypatch):
    socket = Socket()
    install(monkeypatch, socket)
    live = voxtral.VoxtralLiveTranscriber('test', language='en')
    live.open()
    assert live._opened.wait(1)
    assert socket.sent[0]['session']['language'] == 'en'
    with pytest.raises(RuntimeError, match='one recording'):
        live.open()
    live.cancel()
    live._thread.join(1)


def test_final_transcript_does_not_wait_for_socket_close_handshake(monkeypatch):
    close_started, release_close = threading.Event(), threading.Event()
    class SlowCloseSocket(Socket):
        def close(self):
            close_started.set()
            release_close.wait(1)
            super().close()
    socket = SlowCloseSocket()
    install(monkeypatch, socket)
    live = voxtral.VoxtralLiveTranscriber('test')
    live.open()
    live.feed(b'\0\0')
    start = time.monotonic()
    try:
        assert live.finish(1) == 'Hello Holo!'
        assert time.monotonic() - start < .25
        assert close_started.wait(.25)
        assert not socket.closed  # cleanup is still pending, transcript is usable
    finally:
        release_close.set()
        live._thread.join(1)
    assert socket.closed and not live._thread.is_alive()


def test_missing_key_never_opens_network(monkeypatch):
    monkeypatch.delenv('MISTRAL_API_KEY', raising=False)
    monkeypatch.setattr(voxtral, 'connect', lambda *a, **k: pytest.fail('No key must not connect'))
    live = voxtral.VoxtralLiveTranscriber()
    live.open()
    assert live.finish(.2) is None
    assert live._failed == 'Voxtral realtime transcription unavailable.'


def test_batch_uses_mistral_only_auto_language_and_repeated_vocabulary(monkeypatch, tmp_path):
    audio = tmp_path/'private-name.wav'
    audio.write_bytes(b'fake-wav')
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        assert kwargs['files']['file'][1].read() == b'fake-wav'
        return httpx.Response(200, json={'text': ' Bonjour Holo. '})
    monkeypatch.setattr(voxtral.httpx, 'post', post)
    client = voxtral.VoxtralTranscriber('test', language='fr-en')
    assert client.transcribe(str(audio), ['Holo','H Company']) == 'Bonjour Holo.'
    url, request = calls[0]
    assert url == voxtral.FILE_URL
    assert request['data'] == {'model': voxtral.FILE_MODEL, 'context_bias': ['Holo', 'H Company']}
    assert request['files']['file'][0] == 'speech.wav'
    assert request['follow_redirects'] is False


@pytest.mark.parametrize('fault', ['http', 'transport', 'invalid'])
def test_batch_errors_do_not_expose_key_or_provider_body(monkeypatch, tmp_path, fault):
    audio = tmp_path/'audio.wav'
    audio.write_bytes(b'audio')
    def post(*a, **k):
        if fault == 'transport':
            raise RuntimeError('secret-api-key')
        return httpx.Response(401, text='secret-api-key') if fault == 'http' else httpx.Response(200, json={})
    monkeypatch.setattr(voxtral.httpx, 'post', post)
    with pytest.raises(RuntimeError) as exc:
        voxtral.VoxtralTranscriber('secret-api-key').transcribe(str(audio))
    assert 'secret-api-key' not in str(exc.value)
