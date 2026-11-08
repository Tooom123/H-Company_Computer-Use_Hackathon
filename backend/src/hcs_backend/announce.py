"""Zak, the voice of the Cognition (Devin) debug: the support side hears each step of an auto-fix.

A different voice from the assistant's (Sarah guides the user; Zak speaks for the engineering side), so the
room can tell "the user is being helped" from "a bug is being fixed". Announced on transitions only:
fix requested, Devin needs us, pull request opened, Devin stopped without a fix. Never blocks the request
that triggered it: synthesis and playback run on one background thread, one sentence after the other.

Config (backend/.env): ELEVEN (or ELEVENLABS_API_KEY), ID_ZAK (or HCS_FIX_VOICE_ID) = the ElevenLabs voice id,
HCS_FIX_VOICE=0 to mute. Playback: afplay (macOS), aplay / paplay (Linux); none = silent, never an error.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any, Callable

API = "https://api.elevenlabs.io/v1/text-to-speech"
MODEL = "eleven_flash_v2_5"
RATE = 22050

Synth = Callable[[str], bytes]  # text -> PCM 16-bit mono at RATE
Player = Callable[[Path], None]  # plays a WAV file to the end


def _name(fix: dict[str, Any]) -> str:
    """How to say the software: its name from the case, else the repo name without owner and dashes."""
    if fix.get("software"):
        return str(fix["software"])
    repo = str(fix.get("repo") or "the product").split("/")[-1]
    return repo.replace("-", " ").replace("_", " ")


def fix_lines(old: dict[str, Any] | None, new: dict[str, Any]) -> list[str]:
    """What Zak says when a fix moves from `old` to `new` (None = just requested). Transitions only."""
    sw = _name(new)
    if old is None:
        if new.get("status") == "error":
            return [f"I could not start Devin on {sw}. The case stays with support."]
        line = f"Bug found in {sw}. I've asked Devin to fix it on a separate branch."
        return [line + (" This one is simulated." if new.get("simulated") else "")]
    out: list[str] = []
    if new.get("pr_url") and not old.get("pr_url"):
        out.append(f"Devin opened a pull request on {sw}. It's ready for your review.")
    elif (new.get("status_detail") == "waiting_for_user" and old.get("status_detail") != "waiting_for_user"
          and not new.get("pr_url")):
        out.append("Devin needs you. Check the case in the support dashboard.")
    if new.get("status") != old.get("status"):
        if new.get("status") == "error":
            out.append("Devin stopped without a fix.")
        elif new.get("status") == "exit" and not new.get("pr_url"):
            out.append("Devin finished, but no pull request was opened.")
    return out


def elevenlabs_synth(api_key: str, voice_id: str, model: str = MODEL) -> Synth:
    def synth(text: str) -> bytes:
        req = urllib.request.Request(
            f"{API}/{voice_id}?output_format=pcm_{RATE}", method="POST",
            data=json.dumps({"text": text, "model_id": model}).encode(),
            headers={"xi-api-key": api_key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"ElevenLabs {e.code}: {e.read()[:160]!r}") from e

    return synth


def system_player() -> Player | None:
    for cmd in (["afplay"], ["aplay", "-q"], ["paplay"]):
        if (cmd[0] == "afplay") != (sys.platform == "darwin"):
            continue
        if shutil.which(cmd[0]):
            return lambda path, cmd=cmd: subprocess.run(
                [*cmd, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
    return None


class Announcer:
    def __init__(self, synth: Synth, player: Player, cache_dir: Path) -> None:
        self._synth, self._player = synth, player
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._q: queue.Queue = queue.Queue()
        self.spoken: list[str] = []
        self.errors: list[str] = []
        threading.Thread(target=self._run, name="zak", daemon=True).start()

    def say(self, *lines: str) -> None:
        for line in lines:
            if line and line.strip():
                self._q.put(line.strip())

    def wait_idle(self, timeout: float = 30.0) -> bool:
        done = threading.Event()
        self._q.put(done)
        return done.wait(timeout)

    def _clip(self, text: str) -> Path:
        path = self.cache_dir / (hashlib.sha1(text.encode()).hexdigest()[:20] + ".wav")
        if not path.exists():
            pcm = self._synth(text)
            tmp = path.with_suffix(".part")
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm)
            tmp.replace(path)
        return path

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if isinstance(item, threading.Event):
                item.set()
                continue
            try:
                self._player(self._clip(item))
                self.spoken.append(item)
            except Exception as exc:  # noqa: BLE001 - a voice problem never touches the fix itself
                self.errors.append(str(exc))
                if len(self.errors) == 1:
                    print(f"(Zak voice unavailable: {exc})", flush=True)


def make_announcer() -> Announcer | None:
    if os.environ.get("HCS_FIX_VOICE", "1").lower() in {"0", "false", "no", "off"}:
        return None
    key = (os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN") or "").strip()
    voice = (os.environ.get("HCS_FIX_VOICE_ID") or os.environ.get("ID_ZAK") or "").strip()
    if not key or not voice:
        return None
    player = system_player()
    if player is None:
        return None
    cache = Path(tempfile.gettempdir()) / "hcs-tts" / f"zak-{voice}-{MODEL}"
    return Announcer(elevenlabs_synth(key, voice), player, cache)
