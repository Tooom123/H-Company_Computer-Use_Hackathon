"""Text rehearsals use the real event loop without claiming a microphone validation."""
import json
import threading
from unittest.mock import Mock

import pytest

from hcs_agent import coach_v2_runtime as runtime
from hcs_agent import control, inputs, voice


@pytest.fixture
def coach(tmp_path, monkeypatch):
    monkeypatch.setenv("HCS_V2_REHEARSAL", "1")
    monkeypatch.setattr(control, "ControlServer", Mock())
    monkeypatch.setattr(inputs.InputHub, "get", Mock(return_value=Mock()))
    ptt = Mock()
    ptt.wait_transcript.return_value = None
    monkeypatch.setattr(voice, "PushToTalk", Mock(return_value=ptt))
    monkeypatch.setattr(runtime, "ThreadPoolExecutor", Mock())
    monkeypatch.setattr(runtime, "make_tour_cache", Mock())
    speaker = Mock()
    speaker.speaking = False
    obj = runtime.Runtime(tmp_path, "not-a-key", Mock(), speaker, Mock())
    obj.autonomy = 2
    obj.request_decision = Mock()
    obj.control.check_presence = Mock()
    return obj


def events(coach, kind):
    return [e["payload"] for e in map(json.loads, (coach.current.runs_dir / "events.jsonl").read_text().splitlines())
            if e["type"] == kind]


def rehearse(coach, question):
    return coach.control.handle("POST", "/rehearse", {"question": question})


def test_rehearsal_is_opt_in_and_checks_input(coach, monkeypatch):
    monkeypatch.delenv("HCS_V2_REHEARSAL")
    assert rehearse(coach, "Show me the cloud.")[0] == 404
    monkeypatch.setenv("HCS_V2_REHEARSAL", "1")
    assert rehearse(coach, "   ")[0] == 400
    assert rehearse(coach, "x" * 2001)[0] == 400
    assert coach.control.handle("GET", "/rehearse", {"question": "hello"})[0] == 400
    assert coach.events.empty()


def test_only_latest_rehearsal_runs_and_source_is_explicit(coach):
    assert rehearse(coach, "Old request")[0] == 202
    status, body = rehearse(coach, "New request")
    assert status == 202 and body["voice_validated"] is False
    coach.tick()
    assert coach.current.request.goal == "New request"
    coach.request_decision.assert_called_once()
    assert events(coach, "input_source") == [{"source": "text_rehearsal", "voice_validated": False}]


def test_stop_discards_queued_rehearsal_before_any_decision(coach):
    rehearse(coach, "Must not run")
    coach.cancel()
    coach.tick()
    assert coach.current is None
    coach.request_decision.assert_not_called()


def test_rehearsed_stop_or_feedback_does_not_invent_a_run(coach):
    rehearse(coach, "stop")
    coach.tick()
    assert coach.current is None
    coach.feedback.consume_transcript = Mock(return_value=True)
    rehearse(coach, "This is my feedback")
    coach.tick()
    assert coach.current is None
    coach.request_decision.assert_not_called()


def test_rehearsal_never_inherits_interrupted_dictation_timing(coach):
    coach.voice_event("released")
    rehearse(coach, "Show me my plan")
    coach.tick()
    assert events(coach, "request_timing") == [{"input": "text", "dictation_release_to_request_ms": None}]


def test_stop_during_rehearsal_enqueue_cannot_become_the_rehearsal_generation(coach):
    cancelled, resume, stopped = threading.Event(), threading.Event(), threading.Event()
    original_cancel = coach.cancel

    def pause_after_cancel(message="Stopped by you."):
        result = original_cancel(message)
        if message == "Interrupted by a text rehearsal.":
            cancelled.set()
            assert resume.wait(2)
        return result

    coach.cancel = pause_after_cancel
    requester = threading.Thread(target=lambda: rehearse(coach, "Must not run after Stop"))
    stopper = threading.Thread(target=lambda: (original_cancel(), stopped.set()))
    requester.start()
    try:
        assert cancelled.wait(1)
        stopper.start()
        # Without the shared lock, Stop completes inside the enqueue gap. With
        # it, Stop follows the complete enqueue and still invalidates that run.
        stopped.wait(.1)
    finally:
        resume.set()
        requester.join(2)
        stopper.join(2)
    assert not requester.is_alive() and not stopper.is_alive()
    coach.tick()
    assert coach.current is None
    coach.request_decision.assert_not_called()
