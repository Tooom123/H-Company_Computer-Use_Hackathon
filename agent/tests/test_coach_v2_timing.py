"""Measure actual playback launches, not queued speech or a claimed acoustic latency."""
import json
import queue
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

from hcs_agent import coach_v2_runtime as runtime
from hcs_agent.speech import Speaker


def timing_runtime(tmp_path, monkeypatch):
    obj = runtime.Runtime.__new__(runtime.Runtime)
    obj.current = None
    obj.runs_dir = tmp_path
    obj.feedback = SimpleNamespace(consume_transcript=lambda _: False, register=lambda _: None)
    obj.generation = obj.active_generation = 0
    obj.autonomy = 2
    obj.overlay = Mock()
    obj.speaker = Mock()
    obj.response_mode = "both"
    obj.request_decision = Mock()
    obj.events = queue.Queue()
    obj.lock = threading.RLock()
    monkeypatch.setitem(sys.modules, "hcs_agent.overlay", SimpleNamespace(Scene=lambda **kwargs: kwargs))
    return obj


def events(obj, kind):
    return [e["payload"] for e in map(json.loads, (obj.current.runs_dir / "events.jsonl").read_text().splitlines())
            if e["type"] == kind]


def test_release_to_first_playback_and_overlay_order(tmp_path, monkeypatch):
    obj = timing_runtime(tmp_path, monkeypatch)
    now = [10.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: now[0])
    obj.voice_event("released")
    now[0] = 10.4
    obj.start_request("Show me the cloud browser.")
    order = []
    obj.speaker.say.side_effect = lambda *a, **k: order.append("say")
    obj.overlay.show_scene.side_effect = lambda *a, **k: order.append("scene")
    now[0] = 12.0
    obj.show("Here is the cloud browser.")
    assert order == ["say", "scene"]
    assert obj.overlay.show_scene.call_args.kwargs["animate"] is True
    assert events(obj, "speech_started") == []  # queued synthesis isn't audio
    obj.speaker.say.call_args.kwargs["on_started"](12.3)
    first = events(obj, "speech_started")[0]
    assert first == {"step": 0, "first": True, "boundary": "playback_process_started",
                     "speech_request_to_playback_ms": 300, "request_to_playback_ms": 1900,
                     "dictation_release_to_playback_ms": 2300}
    now[0] = 14.0
    obj.show("Your own computer stays free.")
    obj.speaker.say.call_args.kwargs["on_started"](14.1)
    second = events(obj, "speech_started")[1]
    assert second["first"] is False and "dictation_release_to_playback_ms" not in second


def test_cancelled_or_text_only_speech_never_claims_audible_latency(tmp_path, monkeypatch):
    obj = timing_runtime(tmp_path, monkeypatch)
    obj.start_request("Show me my plan.")
    obj.show("Let's open Billing.")
    callback = obj.speaker.say.call_args.kwargs["on_started"]
    obj.cancel()
    callback(runtime.time.monotonic())
    assert events(obj, "speech_started") == []
    obj.response_mode = "text"
    obj.speaker.say.reset_mock()
    obj.show("Text only.")
    obj.speaker.say.assert_not_called()


def test_playback_callback_waits_for_synthesis_and_cancel_drops_it(tmp_path):
    synthesizing, release = threading.Event(), threading.Event()
    started = []

    def synth(_):
        synthesizing.set()
        assert release.wait(2)
        return b"\0\0" * 100

    player = Mock(return_value=SimpleNamespace(poll=lambda: 0))
    sp = Speaker(synth, player, tmp_path)
    try:
        sp.say("Cancelled before playback.", on_started=started.append)
        assert synthesizing.wait(1)
        assert not started
        sp.stop()
        release.set()
        assert sp.wait_idle(2)
        assert not started and not player.called
        sp.say("Played.", "Second sentence.", on_started=started.append)
        assert sp.wait_idle(2)
        assert len(started) == 1 and player.call_count == 2
    finally:
        release.set()
        sp.close()


def test_playback_callback_can_stop_and_failure_does_not_kill_audio_worker(tmp_path):
    player = Mock(return_value=SimpleNamespace(poll=lambda: 0))
    sp = Speaker(lambda _: b"\0\0" * 100, player, tmp_path)
    try:
        sp.say("First", "Must be cancelled", on_started=lambda _: sp.stop())
        assert sp.wait_idle(2)  # callback executes outside Speaker's lock
        assert sp.spoken == ["First"]

        def failed_metric(_):
            raise OSError("The private journal is unavailable")

        sp.say("Still audible", on_started=failed_metric)
        assert sp.wait_idle(2)
        sp.say("Worker is still alive")
        assert sp.wait_idle(2)
        assert sp.spoken == ["First", "Still audible", "Worker is still alive"]
    finally:
        sp.close()
