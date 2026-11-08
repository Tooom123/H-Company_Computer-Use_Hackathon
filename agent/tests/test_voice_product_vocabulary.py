"""Verify real request construction, not recognition quality, without audio/network."""

import json
import sys
from types import SimpleNamespace

import pytest

from hcs_agent import voice


@pytest.mark.parametrize("provider", ["live", "prerecorded"])
def test_automatic_product_names_reach_both_providers_without_rewriting_transcripts(monkeypatch, provider):
    captured = []
    # The ASR mistake must remain visible to the app's contextual clarification;
    # vocabulary hints are not permission to silently change the user's request.
    transcript = "Hello, give me a quick welcome to Orkney."
    vocabulary = list(voice.AUTO_PRODUCT_VOCABULARY)
    if provider == "live":
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
                    "id": "test-utterance", "is_final": True, "utterance": {"text": transcript},
                }})])

        monkeypatch.setattr(voice.httpx, "post", post)
        monkeypatch.setattr("websockets.sync.client.connect", lambda *_a, **_k: Socket())
        transcriber = voice.LiveTranscriber(api_key="test-only", language="fr-en")
        transcriber._queue.put(None)
        transcriber._run(vocabulary)
        result = transcriber.text_so_far()
        processing = captured[0]["realtime_processing"]
    else:
        def transcribe(path, options):
            assert path == "unused.wav"
            captured.append(options)
            return {"result": {"transcription": {"full_transcript": transcript}}}

        client = SimpleNamespace(transcribe=transcribe)
        monkeypatch.setitem(sys.modules, "gladiaio_sdk", SimpleNamespace(
            GladiaClient=lambda **_kw: SimpleNamespace(prerecorded=lambda: client)))
        transcriber = voice.Transcriber(api_key="test-only", language="fr-en")
        result = transcriber.transcribe("unused.wav", vocabulary)
        processing = captured[0]

    assert len(captured) == 1
    assert captured[0]["language_config"] == {"languages": ["fr", "en"], "code_switching": True}
    assert processing["custom_vocabulary"] is True
    config = processing["custom_vocabulary_config"]
    names = {entry["value"] for entry in config["vocabulary"]}
    assert {"H Company", "H Platform", "Holo", "H Companion", "Devin", "Cognition",
            "Odoo", "SAP", "ComfyUI", "Comfy Cloud", "CapCut"} == names
    assert "Acme Demo" not in names and "welcome tour" not in names
    assert config["default_intensity"] == 0.3
    assert all(entry["intensity"] == 0.3 for entry in config["vocabulary"])
    assert not processing.get("translation", False)
    assert result == transcript
