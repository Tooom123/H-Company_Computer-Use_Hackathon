"""Mistral Voxtral speech-to-text; audio never falls back to another provider.

Realtime protocol: https://docs.mistral.ai/studio/audio/speech-to-text/transcribe-in-realtime
File fallback: https://docs.mistral.ai/studio/audio/speech-to-text/transcribe-files
"""
from __future__ import annotations

import base64
import json
import os
import queue
import re
import threading
import time
from urllib.parse import urlencode

import httpx
from websockets.sync.client import connect


REALTIME_MODEL = "voxtral-mini-transcribe-realtime-3"
FILE_MODEL = "voxtral-mini-transcribe-3"
REALTIME_URL = "wss://api.mistral.ai/v1/audio/transcriptions/realtime"
FILE_URL = "https://api.mistral.ai/v1/audio/transcriptions"


def _language(language):
    language = language or os.environ.get("HCS_VOICE_LANGUAGE", "fr-en")
    return language if re.fullmatch(r"[a-z]{2}", language) else None


def _vocabulary(words):
    return list(dict.fromkeys(w.strip()[:80] for w in (words or []) if isinstance(w, str) and w.strip()))[:30]


class VoxtralTranscriber:
    """Same-provider WAV fallback when the realtime connection fails."""

    def __init__(self, api_key=None, language=None):
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        self.language = _language(language)
        self.model = os.environ.get("HCS_VOXTRAL_FILE_MODEL", FILE_MODEL)

    def transcribe(self, wav_path, vocabulary=None):
        if not self.api_key:
            raise RuntimeError("Mistral transcription key is missing.")
        data = {"model": self.model}
        if self.language:
            data["language"] = self.language
        bias = _vocabulary(vocabulary)
        if bias:
            data["context_bias"] = bias  # repeated multipart form fields
        try:
            with open(wav_path, "rb") as audio:
                response = httpx.post(FILE_URL, headers={"Authorization": f"Bearer {self.api_key}"},
                                      data=data, files={"file": ("speech.wav", audio, "audio/wav")},
                                      timeout=httpx.Timeout(20, connect=5), follow_redirects=False)
        except Exception:
            # Provider bodies/transport errors may contain request headers or audio URLs.
            raise RuntimeError("Mistral transcription could not complete.") from None
        if response.status_code != 200:
            raise RuntimeError(f"Mistral transcription returned HTTP {response.status_code}.")
        try:
            result = response.json()
            text = result.get("text") if isinstance(result, dict) else None
            if not isinstance(text, str):
                raise ValueError("Missing transcript")
            return text.strip()
        except Exception:
            raise RuntimeError("Mistral transcription could not complete.") from None


class VoxtralLiveTranscriber:
    """One utterance per instance, 16-bit mono PCM streamed during recording.

    Only a transcription.done event counts as success. A timeout, disconnect or
    cancellation returns None so PushToTalk can use the Mistral WAV fallback.
    """

    def __init__(self, api_key=None, language=None, sample_rate=16000):
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        self.language = _language(language)
        self.sample_rate = sample_rate
        self.model = os.environ.get("HCS_VOXTRAL_REALTIME_MODEL", REALTIME_MODEL)
        self.on_partial = None
        self._queue = queue.Queue(maxsize=512)
        self._cancelled = threading.Event()
        self._done = threading.Event()
        self._opened = threading.Event()
        self._ws = None
        self._thread = None
        self._full = None
        self._partial = ""
        self._failed = None
        self._ended = False
        self._used = False

    def open(self, vocabulary=None):
        if self._used:
            raise RuntimeError("A Voxtral live instance handles one recording.")
        self._used = True
        self._thread = threading.Thread(target=self._run, args=(_vocabulary(vocabulary),),
                                        daemon=True, name="voxtral-live")
        self._thread.start()

    def feed(self, pcm16):
        if self._cancelled.is_set() or self._done.is_set() or self._ended:
            return
        if not isinstance(pcm16, bytes) or len(pcm16) % 2:
            self._failed = "Invalid PCM audio."
            self.cancel()
            return
        try:
            self._queue.put_nowait(pcm16)
        except queue.Full:
            self._failed = "Voxtral audio queue is full."
            self.cancel()

    def _event(self, raw):
        event = json.loads(raw)
        if not isinstance(event, dict) or event.get("type") == "error":
            raise ValueError("Voxtral event rejected")
        return event

    def _run(self, vocabulary):
        ws = None
        try:
            if not self.api_key:
                raise ValueError("Missing key")
            ws = connect(REALTIME_URL + "?" + urlencode({"model": self.model}),
                         additional_headers={"Authorization": f"Bearer {self.api_key}"},
                         open_timeout=5, close_timeout=.5, max_size=1024 * 1024)
            self._ws = ws
            if self._cancelled.is_set():
                return
            if self._event(ws.recv(timeout=3)).get("type") != "session.created":
                raise ValueError("Missing session creation")
            if self._cancelled.is_set():
                return
            settings = {"audio_format": {"encoding": "pcm_s16le", "sample_rate": self.sample_rate},
                        "target_streaming_delay_ms": 480, "context_bias": vocabulary}
            if self.language:
                settings["language"] = self.language
            ws.send(json.dumps({"type": "session.update", "session": settings}))
            updated = self._event(ws.recv(timeout=3))
            if updated.get("type") != "session.updated":
                raise ValueError("Missing session configuration")
            applied = updated.get("session", {}).get("audio_format")
            if applied != settings["audio_format"]:
                raise ValueError("Audio format was not applied")
            self._opened.set()
            deadline = time.monotonic() + 120
            end_sent = False
            while not self._cancelled.is_set() and time.monotonic() < deadline:
                # Bound each send batch so incoming deltas are read during long speech.
                if not end_sent:
                    for _ in range(8):
                        try:
                            chunk = self._queue.get_nowait()
                        except queue.Empty:
                            break
                        if chunk is None:
                            ws.send(json.dumps({"type": "input_audio.end"}))
                            end_sent = True
                            break
                        ws.send(json.dumps({"type": "input_audio.append",
                                            "audio": base64.b64encode(chunk).decode("ascii")}))
                try:
                    event = self._event(ws.recv(timeout=.05))
                except TimeoutError:
                    continue
                kind = event.get("type")
                if kind == "transcription.text.delta":
                    text = event.get("text")
                    if not isinstance(text, str):
                        raise ValueError("Invalid delta")
                    self._partial += text
                    if self.on_partial and not self._cancelled.is_set():
                        self.on_partial(self._partial)
                elif kind == "transcription.done":
                    if not end_sent:
                        raise ValueError("Transcript ended before audio")
                    text = event.get("text")
                    if not isinstance(text, str):
                        raise ValueError("Missing final text")
                    self._full = text.strip()
                    return
        except Exception:
            self._failed = "Voxtral realtime transcription unavailable."
        finally:
            self._opened.set()
            self._done.set()
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def text_so_far(self):
        return self._partial

    def finish(self, timeout=3.0):
        if self._cancelled.is_set():
            return None
        self._ended = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            self.cancel()
            return None
        complete = self._done.wait(max(0, timeout))
        if complete:
            # The worker owns socket cleanup after signalling the final result.
            # Waiting for a second close handshake here adds latency after all
            # transcription work has already finished.
            return (self._full or None) if not self._failed and not self._cancelled.is_set() else None
        self.cancel()
        return None

    def cancel(self):
        self._cancelled.set()
        self._done.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
