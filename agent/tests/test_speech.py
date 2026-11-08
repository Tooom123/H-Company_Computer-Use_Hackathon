"""Spoken notes: cache, prefetch, interruption, sync hold. No key, no audio: fake synth and fake player."""

from __future__ import annotations

import threading
import time
import wave
from pathlib import Path

import pytest

from hcs_agent import speech
from hcs_agent.speech import Speaker, clean, write_wav


class FakeProc:
    def __init__(self, seconds: float) -> None:
        self.end = time.time() + seconds
        self.killed = False

    def poll(self):
        return 0 if (self.killed or time.time() >= self.end) else None

    def terminate(self):
        self.killed = True


class Rig:
    def __init__(self, tmp_path, synth_delay=0.0, play_s=0.05, fail=False):
        self.calls: list[str] = []
        self.played: list[FakeProc] = []
        self.lock = threading.Lock()

        def synth(text: str) -> bytes:
            with self.lock:
                self.calls.append(text)
            time.sleep(synth_delay)
            if fail:
                raise RuntimeError("401 bad key")
            return b"\x00\x00" * 100

        def player(path):  # play_s: seconds for every clip, or a list (one per clip, last one repeats)
            durations = play_s if isinstance(play_s, list) else [play_s]
            p = FakeProc(durations[min(len(self.played), len(durations) - 1)])
            self.played.append(p)
            return p

        self.sp = Speaker(synth, player, tmp_path / "cache", max_hold_s=1.0)


def test_clean_reads_like_the_note():
    assert clean('  Click  **New** → type "Acme"… ') == "Click New then type Acme."
    assert clean("Press ⌘H") == "Press Command H"
    assert clean("   ") == ""


def test_wav_header(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p, b"\x01\x00" * 2205)
    with wave.open(str(p)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 22050, 2205)


def test_says_segments_in_order_and_caches(tmp_path):
    r = Rig(tmp_path)
    r.sp.say("Click New", "It opens a card")
    assert r.sp.wait_idle(3)
    assert r.sp.spoken == ["Click New", "It opens a card"]
    r.sp.say("Click New")
    assert r.sp.wait_idle(3)
    assert r.calls == ["Click New", "It opens a card"]  # second time from the disk cache
    assert r.sp.spoken[-1] == "Click New"


def test_prefetch_makes_the_step_instant(tmp_path):
    r = Rig(tmp_path, synth_delay=0.3)
    r.sp.prefetch(["Step one", "Step two", "Step one", ""])
    r.sp._prefetcher.join(3)
    assert sorted(r.calls) == ["Step one", "Step two"]
    t0 = time.time()
    r.sp.say("Step two")
    while r.sp.holding():
        time.sleep(0.005)
    assert time.time() - t0 < 0.2  # audible almost at once: no synthesis on the way
    assert r.calls.count("Step two") == 1


def test_say_during_prefetch_does_not_synthesise_twice(tmp_path):
    r = Rig(tmp_path, synth_delay=0.3)
    r.sp.prefetch(["Click Save"])
    time.sleep(0.05)
    r.sp.say("Click Save")
    assert r.sp.wait_idle(3)
    assert r.calls == ["Click Save"]


def test_new_step_interrupts_the_previous_sentence(tmp_path):
    r = Rig(tmp_path, play_s=[5.0, 0.05])
    r.sp.say("Step one, a long sentence")
    while not r.played:
        time.sleep(0.005)
    r.sp.say("Step two")
    assert r.sp.wait_idle(3)
    assert r.played[0].killed
    assert r.sp.spoken == ["Step one, a long sentence", "Step two"]


def test_narration_does_not_cut_and_only_latest_waits(tmp_path):
    r = Rig(tmp_path, play_s=0.3)
    r.sp.say("Opening the card", interrupt=False)
    while not r.played:
        time.sleep(0.005)
    r.sp.say("Typing the name", interrupt=False)
    r.sp.say("Saving", interrupt=False)  # replaces "Typing the name", which never got its turn
    assert r.sp.wait_idle(3)
    assert not r.played[0].killed
    assert r.sp.spoken == ["Opening the card", "Saving"]


def test_stop_silences_and_drops_pending(tmp_path):
    r = Rig(tmp_path, play_s=5.0)
    r.sp.say("One", "Two")
    while not r.played:
        time.sleep(0.005)
    r.sp.stop()
    assert r.sp.wait_idle(2)
    assert r.played[0].killed and r.sp.spoken == ["One"]
    assert not r.sp.holding()


def test_holding_until_audible_then_released(tmp_path):
    r = Rig(tmp_path, synth_delay=0.2)
    r.sp.say("Click New")
    assert r.sp.holding()  # the overlay waits for the voice
    while r.sp.holding():
        time.sleep(0.005)
    assert r.played  # released because the audio started, not by the timeout
    assert not r.sp.holding()


def test_hold_is_bounded_when_the_api_is_slow(tmp_path):
    r = Rig(tmp_path, synth_delay=2.0)
    r.sp.max_hold_s = 0.2
    r.sp.say("Slow")
    time.sleep(0.3)
    assert not r.sp.holding()  # the note is drawn anyway; the voice follows when it can
    r.sp.stop()


def test_api_failure_is_silent_and_releases(tmp_path, capsys):
    r = Rig(tmp_path, fail=True)
    r.sp.say("Click New")
    assert r.sp.wait_idle(2)
    assert not r.sp.holding() and not r.played
    r.sp.say("Again")
    assert r.sp.wait_idle(2)
    assert capsys.readouterr().out.count("voice unavailable") == 1


def test_make_speaker_off_without_key_or_when_muted(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no backend/.env up the tree from here
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVEN", raising=False)
    monkeypatch.setenv("HCS_TTS_PROVIDER", "elevenlabs")
    monkeypatch.setenv("HCS_TTS", "1")
    assert speech.make_speaker() is None
    monkeypatch.setenv("ELEVEN", "k")
    monkeypatch.setenv("HCS_TTS", "0")
    assert speech.make_speaker() is None


def test_key_read_from_backend_env(monkeypatch, tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / ".env").write_text("ELEVEN=from-file\n")
    (tmp_path / "agent").mkdir()
    monkeypatch.chdir(tmp_path / "agent")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVEN", raising=False)
    assert speech._api_key() == "from-file"
    monkeypatch.setenv("ELEVENLABS_API_KEY", "from-env")
    assert speech._api_key() == "from-env"


def test_macos_synthesis_is_file_only_and_text_is_stdin(monkeypatch):
    calls = []
    pcm = b"\x01\x00" * 100

    def run(args, **kwargs):
        calls.append((args, kwargs))
        write_wav(Path(args[args.index("-o") + 1]), pcm)

    monkeypatch.setattr(speech.subprocess, "run", run)
    text = "-v BadVoice; $(touch /tmp/unwanted) `echo nope` Bonjour !"
    assert speech.macos_synth("/usr/bin/say", "Thomas", 1.2)(text) == pcm
    args, opts = calls[0]
    assert args[0] == "/usr/bin/say" and args[-2:] == ["-f", "-"]
    assert "--file-format=WAVE" in args and "--data-format=LEI16@22050" in args
    assert args[args.index("-v") + 1] == "Thomas"
    assert args[args.index("-r") + 1] == "210"
    assert text not in args and opts["input"] == text
    assert not opts.get("shell", False) and opts["check"] and opts["timeout"] == 20
    assert not Path(args[args.index("-o") + 1]).exists()  # temporary audio removed


@pytest.mark.parametrize("rate,pcm", [(44100, b"\x00\x00"), (22050, b"")])
def test_macos_synthesis_rejects_unusable_audio_and_cleans_up(monkeypatch, rate, pcm):
    paths = []

    def run(args, **kwargs):
        path = Path(args[args.index("-o") + 1])
        paths.append(path)
        write_wav(path, pcm, rate)

    monkeypatch.setattr(speech.subprocess, "run", run)
    with pytest.raises(RuntimeError):
        speech.macos_synth("/usr/bin/say")("Bonjour")
    assert paths and not paths[0].exists()


@pytest.fixture
def provider_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HCS_TTS", "1")
    monkeypatch.setenv("HCS_TTS_PROVIDER", "auto")
    monkeypatch.setenv("HCS_TTS_SPEED", "1.0")
    monkeypatch.setenv("HCS_TTS_MACOS_VOICE", "Thomas")
    monkeypatch.setattr(speech, "_api_key", lambda: None)
    monkeypatch.setattr(speech.sys, "platform", "darwin")
    monkeypatch.setattr(speech.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(speech.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(speech, "system_player", lambda: lambda path: FakeProc(0))
    # Provider creation alone must never synthesise, play, or send an HTTP request.
    monkeypatch.setattr(speech, "macos_synth", lambda *args: lambda text: b"\x00\x00")
    monkeypatch.setattr(speech, "elevenlabs_synth", lambda *args: lambda text: b"\x00\x00")


def test_auto_without_key_uses_macos_and_reports_provider(provider_env):
    sp = speech.make_speaker()
    try:
        assert sp is not None
        assert (sp.provider, sp.voice, sp.speed) == ("macos", "Thomas", 1.0)
        assert not sp.speaking and sp.spoken == []
    finally:
        if sp:
            sp.close()


def test_auto_preserves_elevenlabs_when_key_exists(provider_env, monkeypatch):
    monkeypatch.setattr(speech, "_api_key", lambda: "test-key")
    sp = speech.make_speaker()
    try:
        assert sp is not None and sp.provider == "elevenlabs"
    finally:
        if sp:
            sp.close()


def test_explicit_macos_does_not_read_elevenlabs_key(provider_env, monkeypatch):
    monkeypatch.setenv("HCS_TTS_PROVIDER", "macos")
    monkeypatch.setattr(speech, "_api_key", lambda: pytest.fail("No key needed for local speech"))
    sp = speech.make_speaker()
    try:
        assert sp is not None and sp.provider == "macos"
    finally:
        if sp:
            sp.close()


@pytest.mark.parametrize("failure", ["muted", "linux", "missing-say", "missing-player", "explicit-elevenlabs", "invalid-provider"])
def test_local_fallback_does_not_override_disabled_or_unavailable_audio(provider_env, monkeypatch, failure):
    if failure == "muted":
        monkeypatch.setenv("HCS_TTS", "0")
    elif failure == "linux":
        monkeypatch.setattr(speech.sys, "platform", "linux")
    elif failure == "missing-say":
        monkeypatch.setattr(speech.shutil, "which", lambda _: None)
    elif failure == "missing-player":
        monkeypatch.setattr(speech, "system_player", lambda: None)
    elif failure == "explicit-elevenlabs":
        monkeypatch.setenv("HCS_TTS_PROVIDER", "elevenlabs")
    else:
        monkeypatch.setenv("HCS_TTS_PROVIDER", "invalid")
    assert speech.make_speaker() is None


def test_stop_during_local_synthesis_prevents_late_playback(provider_env, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    played = []

    def synth(text):
        entered.set()
        assert release.wait(2)
        return b"\x00\x00" * 100

    monkeypatch.setattr(speech, "macos_synth", lambda *args: synth)
    monkeypatch.setattr(speech, "system_player", lambda: lambda path: played.append(path))
    sp = speech.make_speaker()
    try:
        sp.say("Instruction")
        assert entered.wait(1)
        sp.stop()  # same hook used by PTT recording and Stop
        assert not sp.holding()
        release.set()
        assert sp.wait_idle(2)
        assert played == [] and sp.spoken == []
    finally:
        release.set()
        sp.close()


def test_local_playback_mute_and_close_use_existing_interruptible_player(provider_env, monkeypatch):
    played = []

    def player(path):
        proc = FakeProc(5)
        played.append(proc)
        return proc

    monkeypatch.setattr(speech, "system_player", lambda: player)
    sp = speech.make_speaker()
    try:
        sp.muted = True
        sp.say("Muted")
        assert sp.wait_idle(1) and not played
        sp.muted = False
        sp.say("Playing")
        deadline = time.time() + 1
        while not played and time.time() < deadline:
            time.sleep(0.005)
        assert played
        sp.close()
        assert played[0].killed and sp.wait_idle(2)
    finally:
        sp.close()
