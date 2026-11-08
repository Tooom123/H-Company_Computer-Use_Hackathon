"""Spoken notes: the assistant reads aloud what the overlay writes on screen.

Synchronisation with the overlay:
- `say()` is called right before a scene is shown; the overlay holds the pencil reveal while `holding()` is
  true (audio not started yet, at most `max_hold_s`), so the drawing and the voice start together;
- a new guide step interrupts the previous sentence (the screen moved on, so does the voice); takeover
  narration does not cut a sentence, it only keeps the latest one waiting;
- the user acting, a stop, or push-to-talk (the mic must not hear us) silence it at once (`stop()`).

Latency: ~1 s per sentence from ElevenLabs. The guide steps of a procedure are known before they are shown,
so `prefetch()` synthesises them in the background; every clip is cached on disk (keyed by voice, model and
text), so a repeated step or a second demo take plays instantly.

Config: HCS_TTS_PROVIDER=auto (ElevenLabs when configured, otherwise macOS locally), elevenlabs or macos.
ELEVENLABS_API_KEY (or ELEVEN; also read from backend/.env), HCS_TTS=0 to mute, HCS_TTS_VOICE
(voice id, default Sarah), HCS_TTS_MODEL (default eleven_flash_v2_5), HCS_TTS_SPEED (0.7-1.2).
HCS_TTS_MACOS_VOICE selects an installed macOS voice; unset uses the system voice. Local synthesis
uses `say` into a temporary WAV, without speaking during prefetch or sending the text over the network.
Playback: afplay on macOS (aplay / paplay elsewhere); no audio player = no speech, never an error.
"""

from __future__ import annotations

import hashlib
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Protocol

API = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"  # Sarah: young, warm, reassuring (premade voice, every account has it)
DEFAULT_MODEL = "eleven_flash_v2_5"  # lowest latency
SAMPLE_RATE = 22050  # pcm_22050: raw 16-bit mono, wrapped in a WAV header locally (no decoder needed)


class Playback(Protocol):
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...


Synth = Callable[[str], bytes]  # text -> raw PCM 16-bit mono at SAMPLE_RATE
Player = Callable[[Path], Playback]


def clean(text: str) -> str:
    """What the note says, as it should be heard: no symbols, no ellipsis, no doubled spaces."""
    t = (text or "").replace("⌘", "Command ").replace("⋮", "the menu").replace("…", ".").replace("→", "then")
    t = re.sub(r"[*_`#\"“”«»]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def write_wav(path: Path, pcm: bytes, rate: int = SAMPLE_RATE) -> None:
    tmp = path.with_suffix(".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    tmp.replace(path)  # atomic: a concurrent reader never sees half a file


def elevenlabs_synth(api_key: str, voice: str = DEFAULT_VOICE, model: str = DEFAULT_MODEL,
                     speed: float = 1.0) -> Synth:
    import httpx

    client = httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), headers={"xi-api-key": api_key})

    def synth(text: str) -> bytes:
        r = client.post(f"{API}/{voice}", params={"output_format": f"pcm_{SAMPLE_RATE}"},
                        json={"text": text, "model_id": model,
                              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": speed}})
        if r.status_code != 200:
            raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:160]}")
        return r.content

    return synth


def macos_synth(executable: str, voice: str = "", speed: float = 1.0) -> Synth:
    """Produce PCM locally and silently; the normal player owns all audible output and interruption."""
    def synth(text: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="hcs-local-tts-") as folder:
            path = Path(folder) / "speech.wav"
            args = [executable, "-o", str(path), "--file-format=WAVE",
                    f"--data-format=LEI16@{SAMPLE_RATE}", "-r", str(round(175 * speed))]
            if voice:
                args.extend(["-v", voice])
            # Stdin keeps arbitrary text out of argv/options; no shell, no command interpolation.
            args.extend(["-f", "-"])
            subprocess.run(args, input=text, encoding="utf-8", check=True, timeout=20,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with wave.open(str(path), "rb") as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, SAMPLE_RATE):
                    raise RuntimeError("macOS voice returned an unsupported audio format")
                pcm = wav.readframes(wav.getnframes())
                if not pcm:
                    raise RuntimeError("macOS voice returned no audio")
                return pcm
    return synth


def system_player() -> Player | None:
    """afplay on macOS; aplay / paplay on Linux. None when nothing can play audio."""
    for cmd in (["afplay"], ["aplay", "-q"], ["paplay"]):
        if (cmd[0] == "afplay") != (sys.platform == "darwin"):
            continue
        if shutil.which(cmd[0]):
            return lambda path, cmd=cmd: subprocess.Popen(
                [*cmd, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None


class Speaker:
    """One voice for the whole process. Thread-safe; playback runs on its own worker thread."""

    def __init__(self, synth: Synth, player: Player, cache_dir: Path, *, max_hold_s: float = 1.5,
                 provider: str = "custom", voice: str = "", speed: float = 1.0) -> None:
        self._synth, self._player = synth, player
        self.provider, self.voice, self.speed = provider, voice, speed
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_hold_s = max_hold_s
        self._lock = threading.Lock()
        self._gen = 0  # bumped by every interrupting say() and by stop(): older jobs are dropped
        self._jobs: queue.Queue = queue.Queue()
        self._proc: Playback | None = None
        self._pending_since: float | None = None  # a sentence was requested and is not audible yet
        self._inflight: dict[str, threading.Event] = {}  # text -> synthesis in progress (prefetch or say)
        self._warned = False
        self._closed = False
        self._busy = False  # the worker is on a job (synthesising or playing one of its segments)
        self.muted = False  # set from the desktop app: say() is ignored, prefetch still warms the cache
        self.spoken: list[str] = []  # what was actually played (tests, logs)
        self._worker = threading.Thread(target=self._run, name="tts", daemon=True)
        self._worker.start()
        self._prefetcher: threading.Thread | None = None

    # ------------------------------------------------------------------ API (any thread)

    def say(self, *segments: str, interrupt: bool = True) -> None:
        """Speak the segments one after the other (e.g. the note, then its "why")."""
        texts = [t for t in (clean(s) for s in segments) if t]
        if not texts or self._closed or self.muted:
            return
        with self._lock:
            if interrupt:
                self._gen += 1
                self._kill()
            self._drain()  # only the latest request waits: never a backlog of stale sentences
            self._pending_since = time.time()
            self._jobs.put((self._gen, texts))

    def stop(self) -> None:
        """Silence now and forget anything waiting."""
        with self._lock:
            self._gen += 1
            self._kill()
            self._drain()
            self._pending_since = None

    def holding(self) -> bool:
        """True while a requested sentence is not audible yet (bounded): the overlay waits to start drawing."""
        since = self._pending_since
        return since is not None and time.time() - since < self.max_hold_s

    @property
    def speaking(self) -> bool:
        p = self._proc
        return self._busy or self._pending_since is not None or (p is not None and p.poll() is None)

    def prefetch(self, texts: list[str]) -> None:
        """Synthesise upcoming sentences in the background so they play without delay."""
        todo = [t for t in dict.fromkeys(clean(x) for x in texts) if t and not self._path(t).exists()]
        if not todo or self._closed:
            return

        def run() -> None:
            for t in todo:
                if self._closed:
                    return
                self._clip(t)

        self._prefetcher = threading.Thread(target=run, name="tts-prefetch", daemon=True)
        self._prefetcher.start()

    def wait_idle(self, timeout: float = 10.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.speaking and self._jobs.empty():
                return True
            time.sleep(0.02)
        return False

    def close(self) -> None:
        self.stop()
        self._closed = True
        self._jobs.put(None)

    # ------------------------------------------------------------------ internals

    def _path(self, text: str) -> Path:
        return self.cache_dir / (hashlib.sha1(text.encode()).hexdigest()[:20] + ".wav")

    def _clip(self, text: str) -> Path | None:
        """The cached WAV for this text, synthesising it once (concurrent callers wait for the same call)."""
        path = self._path(text)
        if path.exists():
            return path
        with self._lock:
            ev = self._inflight.get(text)
            owner = ev is None
            if owner:
                ev = self._inflight[text] = threading.Event()
        if not owner:
            ev.wait(20)
            return path if path.exists() else None
        try:
            write_wav(path, self._synth(text))
            return path
        except Exception as exc:  # noqa: BLE001 - speech is a bonus: never break the run
            if not self._warned:
                print(f"(voice unavailable: {exc})", flush=True)
                self._warned = True
            return None
        finally:
            with self._lock:
                self._inflight.pop(text, None)
            ev.set()

    def _kill(self) -> None:
        p = self._proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:  # noqa: BLE001
                pass

    def _drain(self) -> None:
        try:
            while True:
                self._jobs.get_nowait()
        except queue.Empty:
            pass

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            self._busy = True
            gen, texts = job
            for text in texts:
                if gen != self._gen:
                    break
                path = self._clip(text)
                with self._lock:
                    if gen != self._gen:
                        break
                    if path is None:
                        self._pending_since = None
                        break
                    try:
                        self._proc = self._player(path)
                    except Exception as exc:  # noqa: BLE001
                        print(f"(voice playback failed: {exc})", flush=True)
                        self._pending_since = None
                        break
                    self._pending_since = None  # audible from now on: the overlay may draw
                    self.spoken.append(text)
                while self._proc.poll() is None:
                    if gen != self._gen:
                        self._kill()
                        break
                    time.sleep(0.02)
            with self._lock:
                if gen == self._gen and self._jobs.empty():
                    self._pending_since = None
                self._busy = False


def _api_key() -> str | None:
    key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN")
    if key:
        return key.strip()
    # The team keeps the ElevenLabs key in backend/.env: look for it from the current directory upwards.
    try:
        from dotenv import dotenv_values
    except ImportError:
        return None
    for d in [Path.cwd(), *Path.cwd().parents]:
        f = d / "backend" / ".env"
        if f.is_file():
            vals = dotenv_values(f)
            key = vals.get("ELEVENLABS_API_KEY") or vals.get("ELEVEN")
            return key.strip() if key else None
    return None


def make_speaker() -> Speaker | None:
    """The process voice, or None when disabled/unavailable. macOS fallback is local and keyless."""
    if os.environ.get("HCS_TTS", "1").lower() in {"0", "false", "no", "off"}:
        return None
    provider = os.environ.get("HCS_TTS_PROVIDER", "auto").lower().strip()
    if provider not in {"auto", "elevenlabs", "macos"}:
        print("(voice off: unsupported HCS_TTS_PROVIDER)", flush=True)
        return None
    key = _api_key() if provider != "macos" else None
    if provider == "auto":
        provider = "elevenlabs" if key else "macos"
    player = system_player()
    if player is None:
        print("(voice off: no audio player found)", flush=True)
        return None
    try:
        speed = min(1.2, max(0.7, float(os.environ.get("HCS_TTS_SPEED", "1.0"))))
    except ValueError:
        speed = 1.0
    if provider == "macos":
        executable = shutil.which("say") if sys.platform == "darwin" else None
        if not executable:
            print("(voice off: no ElevenLabs key or local macOS voice available)", flush=True)
            return None
        voice = os.environ.get("HCS_TTS_MACOS_VOICE", "").strip()
        synth = macos_synth(executable, voice, speed)
        model = "macos-say"
        print("(voice: local macOS synthesis)", flush=True)
    else:
        if not key:
            print("(voice off: no ElevenLabs key — set ELEVENLABS_API_KEY or ELEVEN)", flush=True)
            return None
        voice = os.environ.get("HCS_TTS_VOICE", DEFAULT_VOICE)
        model = os.environ.get("HCS_TTS_MODEL", DEFAULT_MODEL)
        synth = elevenlabs_synth(key, voice, model, speed)
    cache_id = hashlib.sha256(f"{provider}:{voice}:{model}:{speed:g}".encode()).hexdigest()[:20]
    cache = Path(tempfile.gettempdir()) / "hcs-tts" / cache_id
    return Speaker(synth, player, cache, provider=provider, voice=voice or "System", speed=speed)
