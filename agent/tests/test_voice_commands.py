"""No microphone or native listener: audio failures and key releases must not wedge push-to-talk."""

import sys
import threading
from types import SimpleNamespace

import pytest

from hcs_agent import voice
from hcs_agent.inputs import InputHub


class FakeRecorder:
    def __init__(self):
        self.starts = self.stops = self.cancels = 0
        self.fail_start = self.fail_stop = False
        self.entered = threading.Event()
        self.release = None

    def start(self):
        self.starts += 1
        self.entered.set()
        if self.release is not None:
            assert self.release.wait(2)
        if self.fail_start:
            raise RuntimeError("microphone unavailable")

    def stop(self):
        self.stops += 1
        if self.fail_stop:
            raise RuntimeError("device disconnected")
        return None

    def cancel(self):
        self.cancels += 1


@pytest.fixture
def rig(monkeypatch):
    recorder = FakeRecorder()
    hub = SimpleNamespace(set_combo=lambda _: None, subscribe=lambda _: None, unsubscribe=lambda _: None,
                          plain_key_matches=lambda _: False)
    monkeypatch.setattr(InputHub, "get", lambda: hub)
    monkeypatch.setattr(voice, "Recorder", lambda: recorder)
    monkeypatch.setattr(voice, "Transcriber", lambda: SimpleNamespace())
    live = SimpleNamespace(cancelled=False, opened=False)
    live.open = lambda _: setattr(live, 'opened', True)
    live.cancel = lambda: setattr(live, 'cancelled', True)
    live.feed = lambda _: None
    monkeypatch.setattr(voice, "LiveTranscriber", lambda: live)
    states = []
    ptt = voice.PushToTalk(key_name="ctrl+shift+h", on_state=states.append)
    ptt.start()
    yield ptt, recorder, states
    if recorder.release is not None:
        recorder.release.set()
    ptt.stop()
    ptt._worker.join(2)
    assert not ptt._worker.is_alive()


def drain(ptt):
    done = threading.Event()
    threading.Thread(target=lambda: (ptt._commands.join(), done.set()), daemon=True).start()
    assert done.wait(2), "audio command queue stalled"


def test_microphone_start_error_is_visible_and_can_be_retried(rig):
    ptt, recorder, states = rig
    recorder.fail_start = True
    ptt._on_event("combo_down", None)
    drain(ptt)
    assert not ptt._recording and "recording" not in states
    assert states[-1].startswith("error: microphone RuntimeError") and recorder.cancels == 1
    recorder.fail_start = False
    ptt._on_event("combo_down", None)
    drain(ptt)
    assert ptt._recording and states[-1] == "recording"


def test_slow_audio_start_does_not_block_release_delivery(rig):
    ptt, recorder, states = rig
    recorder.release = threading.Event()
    ptt._on_event("combo_down", None)
    assert recorder.entered.wait(1)
    ptt._on_event("combo_up", None)  # must return while microphone start is blocked
    assert ptt._commands.qsize() == 1
    recorder.release.set()
    drain(ptt)
    assert recorder.stops == 1 and not ptt._recording
    assert states == ["starting", "recording", "too_short"]


def test_microphone_stop_error_does_not_leave_recording_state(rig):
    ptt, recorder, states = rig
    recorder.fail_stop = True
    ptt._on_event("combo_down", None)
    ptt._on_event("combo_up", None)
    drain(ptt)
    assert not ptt._recording and states[-1].startswith("error: microphone")
    assert recorder.cancels == 1 and ptt.transcripts.empty()


def test_stop_discards_audio_without_transcription(rig):
    ptt, recorder, states = rig
    ptt._on_event("combo_down", None)
    drain(ptt)
    ptt.stop()
    ptt._worker.join(1)
    assert not ptt._recording and recorder.cancels == 1 and recorder.stops == 0


def test_live_audio_starts_once_and_is_cancelled_on_short_recording(rig):
    ptt, recorder, states = rig
    ptt._on_event('combo_down', None)
    drain(ptt)
    live = ptt._live
    assert live.opened and recorder.starts == 1
    assert recorder.on_chunk == live.feed
    ptt._on_event('combo_up', None)
    drain(ptt)
    assert live.cancelled and ptt._live is None


def test_failed_microphone_closes_live_transcription(rig):
    ptt, recorder, _ = rig
    recorder.fail_start = True
    ptt._on_event('combo_down', None)
    drain(ptt)
    assert ptt._live is None and not ptt._recording


@pytest.mark.parametrize("mods,flags,remaining", [({"cmd"}, 1, 0), ({"ctrl", "shift"}, 12, 4)])
def test_modifier_release_stops_chord_before_main_key_release(monkeypatch, mods, flags, remaining):
    quartz = SimpleNamespace(CGEventGetFlags=lambda e: e["flags"],
        CGEventGetIntegerValueField=lambda e, _: e["keycode"], kCGEventFlagMaskCommand=1,
        kCGEventFlagMaskAlternate=2, kCGEventFlagMaskControl=4, kCGEventFlagMaskShift=8,
        kCGEventFlagsChanged=12, kCGEventKeyDown=10, kCGEventKeyUp=11, kCGKeyboardEventKeycode=9)
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    hub = InputHub.__new__(InputHub)
    hub._combo_mods, hub._combo_keycode, hub._combo_down = mods, 4, False
    events = []
    hub._emit = lambda kind, _: events.append(kind)
    assert hub._intercept(10, {"keycode": 4, "flags": flags}) is None
    hub._intercept(12, {"keycode": 56, "flags": remaining})
    hub._intercept(11, {"keycode": 4, "flags": remaining})
    assert events == ["combo_down", "combo_up"] and not hub._combo_down
