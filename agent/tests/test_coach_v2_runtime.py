"""Exercise the clean coaching loop without AppKit, input hooks, APIs or desktop effects."""

from dataclasses import dataclass
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hcs_agent import coach_v2_runtime as runtime
from hcs_agent.coach_v2 import CoachDecision, CoachProtocolError
from hcs_agent.coach_v2_journal import CoachRun


URL = "https://platform.hcompany.ai/agents/sessions"


@dataclass
class Target:
    name: str = "Sessions"
    role: str = "AXButton"
    box: tuple = (10, 20, 80, 40)
    enabled: bool | None = True

    @property
    def center(self):
        x, y, w, h = self.box
        return x + w / 2, y + h / 2


def observation(target=None, *, captured_at=100.0, url=URL):
    target = target or Target()
    return runtime.Observation({"url": url, "controls": [], "text": []}, {1: target}, captured_at, "Chrome")


@pytest.fixture
def rt(tmp_path, monkeypatch):
    """Bypass physical-I/O construction, exercising the actual state machine methods."""
    obj = runtime.Runtime.__new__(runtime.Runtime)
    obj.runs_dir = tmp_path / "runs"
    obj.api_key = "not-a-real-key"
    obj.overlay = Mock()
    obj.speaker = Mock()
    obj.speaker.holding.return_value = False
    obj.speaker.speaking = False
    obj.desktop = Mock()
    obj.show = Mock()
    obj.events = queue.Queue()
    obj.pool = Mock()
    obj.lock = threading.RLock()
    obj.generation = obj.active_generation = 1
    obj.closed = False
    obj.current = CoachRun(obj.runs_dir, "Show me my sessions.", "guide")
    obj.history, obj.step, obj.pending, obj.due = [], 0, None, None
    obj.busy = False
    obj.autonomy = 0
    obj.response_mode = "both"
    obj.voice_state, obj.last_text = "ready", ""
    obj.started_at = "2026-11-08T00:00:00+00:00"
    obj.ptt = Mock()
    obj.ptt.wait_transcript.return_value = None
    obj.control = Mock()
    obj.control.app_contains.return_value = False
    monkeypatch.setattr(runtime, "foreground_url", lambda: URL)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 100.0)
    return obj


def prepare_guide(rt, decision=None, target=None):
    target = target or Target()
    decision = decision or CoachDecision(action="click", target=1, speech="Open Sessions on the left.")
    rt.accept_decision(1, decision, observation(target), target)
    return decision, target


def test_new_utterance_cancels_before_transcription_and_rejects_old_result(rt):
    decision = CoachDecision(action="click", target=1, speech="Open Sessions.")
    rt.voice_event("starting")
    assert rt.generation == 2
    rt.speaker.stop.assert_called_once()
    rt.accept_decision(1, decision, observation(), Target())
    rt.show.assert_not_called()
    rt.desktop.click.assert_not_called()
    rt.tick()
    assert rt.current.state.value == "stopped"
    assert rt.current.report["verification"]["satisfied"] is False
    assert rt.pending is None and rt.due is None


def test_cancelled_worker_preserves_trace_but_emits_no_stale_decision(rt, monkeypatch):
    observed = observation()
    observer = Mock(return_value=observed)
    monkeypatch.setattr(runtime, "observe", observer)

    class Client:
        last_raw = {"action": "click"}
        last_usage = {"input_tokens": 20}
        closed = False

        def __init__(self, _key):
            pass

        def decide(self, *args):
            rt.cancel("New request")
            return CoachDecision(action="click", target=1, speech="Open Sessions.")

        def close(self):
            Client.closed = True

    monkeypatch.setattr(runtime, "CoachClient", Client)
    rt.decide_worker(rt.current, 1, [])
    assert observer.call_count == 1  # cancelled before fresh observation or display
    events = list(rt.events.queue)
    assert [event[0] for event in events] == ["cancel"]
    assert Client.closed
    text = (rt.current.runs_dir / "events.jsonl").read_text()
    assert '"superseded": true' in text


def test_late_cancel_event_does_not_clear_a_newer_request(rt):
    rt.generation = rt.active_generation = 3
    decision = CoachDecision(action="click", target=1, speech="Open Sessions.")
    rt.accept_decision(3, decision, observation(), Target())
    pending = rt.pending
    rt.overlay.reset_mock()
    rt.events.put(("cancel", 2, "An earlier request was stopped."))
    rt.tick()
    assert rt.pending is pending
    assert not rt.current.state.terminal
    rt.overlay.hide.assert_not_called()


def test_unrelated_click_does_not_advance_guide(rt):
    prepare_guide(rt)
    rt.user_input("click", (300, 300))
    assert rt.pending is not None and rt.due is None
    assert rt.history == []
    rt.pool.submit.assert_not_called()
    rt.desktop.click.assert_not_called()


def test_click_on_companion_does_not_advance_even_when_it_covers_target(rt):
    _, target = prepare_guide(rt)
    rt.control.app_contains.return_value = True
    rt.user_input("click", target.center)
    assert rt.pending is not None and rt.due is None and not rt.history


def test_targeted_click_schedules_fresh_observation_without_claiming_success(rt, monkeypatch):
    _, target = prepare_guide(rt)
    rt.user_input("click", target.center)
    assert rt.pending is None
    assert rt.due[1] == "observe"
    assert rt.history[-1]["verified"] is False
    assert rt.current.report is None and not rt.current.state.terminal
    rt.pool.submit.assert_not_called()  # debounce lets the page respond first
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 101.0)
    rt.tick()
    rt.pool.submit.assert_called_once()
    assert rt.pool.submit.call_args.args[0] == rt.decide_worker
    rt.desktop.click.assert_not_called()  # Guide never clicks for the user


def test_typing_requires_enter_not_merely_clicking_the_field(rt):
    field = Target("Search", "AXTextField")
    decision = CoachDecision(action="type", target=1, text="demo", speech="Type demo in the search field.")
    prepare_guide(rt, decision, field)
    rt.user_input("click", field.center)
    rt.user_input("key_down", SimpleNamespace(name="tab"))
    assert rt.pending is not None and rt.due is None and not rt.history
    rt.user_input("key_down", SimpleNamespace(name="enter"))
    assert rt.pending is None and rt.due[1] == "observe"
    assert rt.current.report is None and rt.history[-1]["verified"] is False


def test_target_ids_are_frame_local_and_unique_control_can_move():
    original = Target()
    moved = Target(box=(60, 90, 80, 40))
    unrelated = Target("Delete session", box=original.box)
    fresh = observation()
    fresh.targets = {1: unrelated, 8: moved}
    assert runtime.matching_target(original, fresh) is moved


def test_duplicate_labels_need_unambiguous_original_frame():
    original = Target()
    exact = Target()
    moved = Target(box=(400, 90, 80, 40))
    fresh = observation()
    fresh.targets = {2: moved, 4: exact}
    assert runtime.matching_target(original, fresh) is exact
    fresh.targets = {2: moved, 4: Target(box=(900, 90, 80, 40))}
    assert runtime.matching_target(original, fresh) is None
    fresh.targets = {1: Target(enabled=False)}
    assert runtime.matching_target(original, fresh) is None


def test_worker_rebinds_target_to_fresh_frame_before_emitting(rt, monkeypatch):
    original = Target()
    fresh_target = Target(box=(100, 150, 80, 40))
    old = observation(original)
    fresh = observation()
    fresh.targets = {7: fresh_target}
    monkeypatch.setattr(runtime, "observe", Mock(side_effect=[old, fresh]))
    client = Mock(last_raw={}, last_usage={})
    client.decide.return_value = CoachDecision(action="click", target=1, speech="Open Sessions.")
    monkeypatch.setattr(runtime, "CoachClient", lambda _key: client)
    rt.decide_worker(rt.current, 1, [])
    event = rt.events.get_nowait()
    assert event[0] == "decision" and event[-1] is fresh_target
    assert event[-2] is fresh
    client.close.assert_called_once()


def test_worker_discards_missing_target_instead_of_using_old_coordinates(rt, monkeypatch):
    old, fresh = observation(), observation(Target("Different control"))
    monkeypatch.setattr(runtime, "observe", Mock(side_effect=[old, fresh]))
    client = Mock(last_raw={}, last_usage={})
    client.decide.return_value = CoachDecision(action="click", target=1, speech="Open Sessions.")
    monkeypatch.setattr(runtime, "CoachClient", lambda _key: client)
    rt.decide_worker(rt.current, 1, [])
    assert rt.events.get_nowait() == ("changed", 1)
    rt.show.assert_not_called()
    rt.desktop.click.assert_not_called()


def test_no_target_is_painted_if_foreground_changed_after_observation(rt, monkeypatch):
    monkeypatch.setattr(runtime, "foreground_url", lambda: "https://example.org/")
    prepare_guide(rt)
    assert rt.current.state.value == "blocked"
    assert rt.pending is None and rt.due is None
    assert all(call.args[1:] == () for call in rt.show.call_args_list)  # only a targetless explanation


@pytest.mark.parametrize("action", [
    CoachDecision(action="click", target=1, speech="Open Sessions."),
    CoachDecision(action="type", target=1, text="demo", speech="Search for demo."),
    CoachDecision(action="scroll", direction="down", speech="Scroll down to read the next section."),
    CoachDecision(action="key", key="enter", speech="Press Enter to search."),
    CoachDecision(action="open_docs", url="https://hub.hcompany.ai/agents-api/overview", speech="Let's open the documentation."),
])
def test_every_effect_requires_the_same_h_foreground_page(action, monkeypatch):
    desktop = Mock()
    monkeypatch.setattr(runtime, "foreground_url", lambda: "https://example.org/")
    with pytest.raises(CoachProtocolError, match="page changed"):
        runtime.perform(action, Target(), URL, desktop)
    assert not desktop.mock_calls


def test_unsupported_typing_is_rejected_before_clicking(monkeypatch):
    from hcs_agent import a11y
    monkeypatch.setattr(runtime, "foreground_url", lambda: URL)
    monkeypatch.setattr(a11y, "visible_at_point", lambda _target: True)
    desktop = Mock()
    decision = CoachDecision(action="type", target=1, text="café", speech="Enter the search term.")
    with pytest.raises(CoachProtocolError, match="enter that text yourself"):
        runtime.perform(decision, Target("Search", "AXTextField"), URL, desktop)
    assert not desktop.mock_calls


def test_act_refreshes_expired_observation_instead_of_clicking(rt, monkeypatch):
    rt.current = CoachRun(rt.runs_dir, "Open my sessions.", "act")
    decision = CoachDecision(action="click", target=1, speech="I'll open Sessions.")
    rt.accept_decision(1, decision, observation(captured_at=70), Target())
    action = Mock()
    monkeypatch.setattr(runtime, "perform", action)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 101.0)
    rt.tick()
    action.assert_not_called()
    rt.pool.submit.assert_called_once()
    assert rt.pending is None


def test_act_executes_one_effect_then_observes_before_another(rt, monkeypatch):
    rt.current = CoachRun(rt.runs_dir, "Open my sessions.", "act")
    decision = CoachDecision(action="click", target=1, speech="I'll open Sessions.")
    target = Target()
    rt.accept_decision(1, decision, observation(target), target)
    action = Mock()
    monkeypatch.setattr(runtime, "perform", action)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 101.0)
    rt.tick()
    action.assert_called_once_with(decision, target, URL, rt.desktop, None)
    assert rt.pending is None and rt.due[1] == "observe"
    assert rt.history[-1]["event"] == "agent_action_executed"
    assert rt.current.report is None
    rt.tick()
    assert action.call_count == 1


def test_model_completion_is_not_a_verified_or_human_label(rt):
    decision = CoachDecision(action="done", speech="You can read the answer here.")
    rt.accept_decision(1, decision, observation(), None)
    assert rt.current.state.terminal
    assert rt.current.report["declared"]["outcome"] == "done"
    assert rt.current.report["verification"]["satisfied"] is False
    assert not (rt.current.runs_dir / "labels.json").exists()
    rt.show.assert_called_once()

@pytest.mark.parametrize('search', [False, True])
def test_enter_only_submits_a_focused_search(monkeypatch, search):
    monkeypatch.setattr(runtime, 'foreground_url', lambda: URL)
    monkeypatch.setattr(runtime, 'focused_search', lambda: search)
    desktop = Mock()
    decision = CoachDecision(action='key', key='enter', speech='Press Enter to search.')
    if search:
        runtime.perform(decision, None, URL, desktop)
        desktop.press.assert_called_once_with('enter')
    else:
        with pytest.raises(CoachProtocolError, match='only submit searches'):
            runtime.perform(decision, None, URL, desktop)
        assert not desktop.mock_calls


def test_actual_user_event_reaches_next_model_history(rt):
    prepare_guide(rt)
    rt.schedule_observation('user_input')
    rt.request_decision()
    sent_history = rt.pool.submit.call_args.args[3]
    assert sent_history[0]['action'] == 'click'
    assert sent_history[0]['observation']['target'] == 'Sessions'
    assert sent_history[0]['observation']['event'] == 'user_input'
    assert sent_history[0]['observation']['verified'] is False


def test_rejected_model_reply_never_blames_screen_visibility():
    error = CoachProtocolError('Holo returned an invalid coaching step.')
    message = runtime.failure_message(error, 'model')
    assert 'could read the page' in message
    assert 'Keep H' not in message and 'visible' not in message


def test_provider_outage_never_blames_screen_visibility():
    error = CoachProtocolError('Holo returned HTTP 503.', kind='provider')
    message = runtime.failure_message(error, 'model')
    assert "couldn't reach Holo" in message
    assert 'page' not in message


def test_unexpected_exception_details_are_not_spoken():
    message = runtime.failure_message(RuntimeError('private HTTP response body'), 'model')
    assert 'private' not in message and 'HTTP' not in message


def test_model_failure_records_model_stage_and_safe_reason(rt, monkeypatch):
    monkeypatch.setattr(runtime, 'observe', lambda: observation())
    client = Mock(last_raw={'speech': 'Hello.'}, last_usage={})
    client.decide.side_effect = CoachProtocolError('invalid coaching step', reason='invalid_fields')
    monkeypatch.setattr(runtime, 'CoachClient', lambda _: client)
    rt.decide_worker(rt.current, 1, [])
    event = rt.events.get_nowait()
    assert event[0] == 'error' and 'could read the page' in event[2]
    import json
    events = [json.loads(line) for line in (rt.current.runs_dir / 'events.jsonl').read_text().splitlines()]
    error = next(item['payload'] for item in events if item['type'] == 'model_error')
    assert error['stage'] == 'model'
    assert error['reason'] == 'invalid_fields'
