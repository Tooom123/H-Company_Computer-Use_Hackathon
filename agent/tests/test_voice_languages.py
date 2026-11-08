"""Assert the actual Gladia request options, without microphone, network or paid calls."""

import json
import sys
from types import SimpleNamespace

import pytest

from hcs_agent import voice


@pytest.mark.parametrize("language,expected", [
    ("fr-en", {"languages": ["fr", "en"], "code_switching": True}),
    ("fr", {"languages": ["fr"], "code_switching": False}),
    ("en", {"languages": ["en"], "code_switching": False}),
])
def test_live_request_language_policy_preserves_provider_transcript(monkeypatch, language, expected):
    captured = []
    spoken = "Où je peux redeem a coupon code?"

    def post(url, **kwargs):
        assert url == voice.LiveTranscriber.INIT_URL
        captured.append(kwargs["json"])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"url": "wss://unused.test"})

    class Socket:
        def send(self, _data):
            pass

        def close(self):
            pass

        def __iter__(self):
            return iter([json.dumps({"type": "transcript", "data": {
                "id": "utterance-1", "is_final": True, "utterance": {"text": spoken},
            }})])

    monkeypatch.setattr(voice.httpx, "post", post)
    monkeypatch.setattr("websockets.sync.client.connect", lambda *_a, **_k: Socket())
    monkeypatch.setenv("HCS_VOICE_LANGUAGE", "fr")
    transcriber = voice.LiveTranscriber(api_key="test-only", language=language)
    transcriber._queue.put(None)  # Sender exits without waiting for microphone data.
    transcriber._run(["Devin"])

    assert len(captured) == 1
    assert captured[0]["language_config"] == expected
    assert not captured[0].get("realtime_processing", {}).get("translation", False)
    assert transcriber.text_so_far() == spoken


@pytest.mark.parametrize("language,expected", [
    ("fr-en", {"languages": ["fr", "en"], "code_switching": True}),
    ("fr", {"languages": ["fr"], "code_switching": False}),
    ("en", {"languages": ["en"], "code_switching": False}),
])
def test_prerecorded_fallback_uses_same_language_policy(monkeypatch, language, expected):
    captured = []
    spoken = "Show me les settings de Devin."

    def transcribe(path, options):
        assert path == "unused.wav"
        captured.append(options)
        return {"result": {"transcription": {"full_transcript": spoken}}}

    client = SimpleNamespace(transcribe=transcribe)
    monkeypatch.setitem(sys.modules, "gladiaio_sdk", SimpleNamespace(
        GladiaClient=lambda **_kwargs: SimpleNamespace(prerecorded=lambda: client)))
    monkeypatch.setenv("HCS_VOICE_LANGUAGE", language)
    transcriber = voice.Transcriber(api_key="test-only")

    assert transcriber.transcribe("unused.wav", ["Devin"]) == spoken
    assert captured[0]["language_config"] == expected
    assert not captured[0].get("translation", False)
    assert voice.LiveTranscriber(api_key="test-only").language == language
