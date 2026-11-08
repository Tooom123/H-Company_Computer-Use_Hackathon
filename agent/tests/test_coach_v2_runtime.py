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
    obj.tour = None
    obj.requires_confirmation = obj.confirmation_pending = False
    obj.approved_step = None
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


def test_terminal_notice_disappears_after_reading_interval(rt, monkeypatch):
    rt.finish('failed', 'Please try your question again.')
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 107.9)
    rt.tick()
    rt.overlay.hide.assert_not_called()
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 108.0)
    rt.tick()
    rt.overlay.hide.assert_called_once()
    assert rt.dismiss_notice is None
    assert rt.current.report['status'] == 'failed'  # dismissing is not erasing the trace


def test_terminal_notice_waits_for_voice_but_has_a_hard_deadline(rt, monkeypatch):
    rt.finish('completed', 'You can find your sessions here.')
    rt.speaker.speaking = True
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 109.0)
    rt.tick()
    rt.overlay.hide.assert_not_called()
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 125.0)
    rt.tick()
    rt.overlay.hide.assert_called_once()


def test_old_notice_timer_cannot_hide_a_new_request(rt, monkeypatch):
    rt.finish('failed', 'Please try again.')
    rt.feedback = Mock()
    rt.feedback.consume_transcript.return_value = False
    rt.request_decision = Mock()
    rt.start_request('Show me Skills.')
    rt.overlay.reset_mock()
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 130.0)
    rt.tick()
    rt.overlay.hide.assert_not_called()
    assert rt.dismiss_notice is None and not rt.current.state.terminal


def test_stop_clears_finished_notice_immediately(rt):
    rt.finish('failed', 'Please try again.')
    rt.cancel()
    rt.tick()
    rt.overlay.hide.assert_called_once()
    assert rt.dismiss_notice is None


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


def test_unicode_multiline_typing_uses_literal_field_writer(monkeypatch):
    from hcs_agent import a11y
    monkeypatch.setattr(runtime, "foreground_url", lambda: URL)
    monkeypatch.setattr(a11y, "visible_at_point", lambda _target: True)
    writer = Mock()
    monkeypatch.setattr(runtime, "set_literal_text", writer)
    desktop = Mock()
    target = Target("Instructions", "AXTextArea")
    text = "# Café\nGuide the user, one step at a time."
    decision = CoachDecision(action="type", target=1, text=text, speech="I'll write the coaching instructions.")
    runtime.perform(decision, target, URL, desktop)
    desktop.click.assert_called_once_with(*target.center)
    writer.assert_called_once_with(target, text, desktop)
    desktop.write.assert_not_called()


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


def tour_decision():
    return CoachDecision(action='tour', speech='H Platform helps you build and run computer-use agents.',
                         points=[{'speech': 'Agents define what your assistant does.', 'target': 1},
                                 {'speech': 'Sessions show its individual runs.', 'target': 2},
                                 {'speech': 'Skills provide reusable instructions.', 'target': 3}])


def test_tour_reads_intro_then_three_fresh_markers_without_clicks_or_recap(rt, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: clock[0])
    targets = {i: Target(name, box=(10, i * 50, 80, 40))
               for i, name in enumerate(['Agents', 'Sessions', 'Skills'], 1)}
    obs = observation(); obs.targets = targets
    monkeypatch.setattr(runtime, 'observe', lambda: obs)
    decision = tour_decision()
    rt.accept_decision(1, decision, obs, None, targets)
    rt.show.assert_called_once_with(decision.speech, None)
    rt.speaker.prefetch.assert_called_once()
    for point in decision.points:
        clock[0] += 1
        rt.speaker.speaking = True
        before = rt.pool.submit.call_count
        rt.tick()
        assert rt.pool.submit.call_count == before
        rt.speaker.speaking = False
        rt.tick()
        submitted = rt.pool.submit.call_args.args
        assert submitted[0] == rt.tour_worker
        submitted[0](*submitted[1:])
        rt.tick()
        assert rt.show.call_args.args == (point.speech, targets[point.target])
    clock[0] += 1
    rt.tick()
    assert rt.current.state.value == 'completed'
    assert rt.show.call_count == 4  # intro + 3 points, no repeated summary
    assert rt.tour is None
    assert not rt.desktop.mock_calls


def test_interrupt_drops_late_tour_point(rt, monkeypatch):
    targets = {i: Target(name) for i, name in enumerate(['Agents', 'Sessions', 'Skills'], 1)}
    obs = observation(); obs.targets = targets
    decision = tour_decision()
    rt.accept_decision(1, decision, obs, None, targets)
    rt.voice_event('starting')
    rt.events.put(('tour_point', 1, decision.points[0], targets[1], URL))
    rt.tick()
    assert rt.tour is None and rt.current.state.value == 'stopped'
    assert rt.show.call_count == 1
    assert not rt.desktop.mock_calls


def test_tour_rematches_moved_target_before_highlighting(rt, monkeypatch):
    point = tour_decision().points[0]
    original = Target('Agents')
    moved = Target('Agents', box=(200, 100, 80, 40))
    fresh = observation(); fresh.targets = {19: moved}
    monkeypatch.setattr(runtime, 'observe', lambda: fresh)
    rt.tour_worker(rt.current, 1, point, original, URL)
    event = rt.events.get_nowait()
    assert event == ('tour_point', 1, point, moved, URL)


def test_cached_tour_skips_holo_but_refreshes_targets(rt, monkeypatch):
    targets = {i: Target(name) for i, name in enumerate(['Agents', 'Sessions', 'Skills'], 1)}
    first = observation(); first.targets = targets
    fresh = observation(); fresh.targets = {i: Target(t.name, box=(30, i * 50, 80, 40))
                                           for i, t in targets.items()}
    observer = Mock(side_effect=[first, fresh])
    monkeypatch.setattr(runtime, 'observe', observer)
    model = Mock()
    monkeypatch.setattr(runtime, 'CoachClient', model)
    rt.tour_cache = Mock()
    rt.tour_cache.get.return_value = tour_decision()
    rt.decide_worker(rt.current, 1, [])
    model.assert_not_called()
    assert observer.call_count == 2
    event = rt.events.get_nowait()
    assert event[0] == 'decision' and event[-1][1] is fresh.targets[1]
    log = (rt.current.runs_dir / 'events.jsonl').read_text()
    assert '"tour_cache_hit"' in log and '"model_call": false' in log
    assert '"type": "model"' not in log


def test_key_form_opener_acts_with_current_list_evidence_despite_reused_ids(rt, monkeypatch):
    url = 'https://platform.hcompany.ai/settings/api-keys'
    monkeypatch.setattr(runtime, 'foreground_url', lambda: url)
    rt.current = CoachRun(rt.runs_dir, 'Create a demo API key for one day.', 'act')
    target = Target('Create an API key')
    decision = CoachDecision(action='click', target=1, speech="I'll open the key form.")
    obs = observation(target, url=url)
    obs.data['controls'] = [{'id': 1, 'label': 'API Keys', 'role': 'AXHeading'},
                            {'id': 4, 'label': target.name, 'role': target.role}]
    rt.accept_decision(1, decision, obs, target)
    assert not rt.requires_confirmation
    assert rt.due[1] == 'act' and rt.current.state.value == 'running'
    assert rt.pending[1] is target


def prepare_key_confirmation(rt, monkeypatch):
    url = 'https://platform.hcompany.ai/api-keys'
    monkeypatch.setattr(runtime, 'foreground_url', lambda: url)
    rt.current = CoachRun(rt.runs_dir, 'Create h-hackathon for one day.', 'act')
    decision = CoachDecision(action='click', target=1, speech="I'll create the API key.")
    target = Target('Create API key')
    obs = observation(target, url=url)
    # The current frame's ID1 is unrelated. Runtime must use rebound target label.
    obs.data['controls'] = [{'id': 1, 'label': 'Sessions', 'role': 'AXButton'}]
    rt.accept_decision(1, decision, obs, target)
    return decision, target, obs


def test_key_creation_waits_for_human_confirmation_then_refreshes_before_one_click(rt, monkeypatch):
    decision, original, obs = prepare_key_confirmation(rt, monkeypatch)
    assert rt.requires_confirmation and rt.due is None
    assert rt.current.state.value == 'awaiting_user'
    rt.show.assert_called_once_with('Create this API key? Confirm in H Companion to continue.', original)
    assert rt.status()['current']['step']['kind'] == 'confirm'
    sid = rt.current.session_id
    assert rt.next_step(sid, rt.step, True)
    assert not rt.next_step(sid, rt.step, True)
    rt.tick()
    submitted = rt.pool.submit.call_args.args
    assert submitted[0] == rt.approved_action_worker
    moved = Target('Create API key', box=(200, 300, 80, 40))
    fresh = observation(moved, url=obs.data['url'])
    monkeypatch.setattr(runtime, 'observe', lambda: fresh)
    submitted[0](*submitted[1:])
    rt.tick()
    assert not rt.requires_confirmation and rt.pending[1] is moved
    action = Mock()
    monkeypatch.setattr(runtime, 'perform', action)
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 101.0)
    rt.tick()
    action.assert_called_once_with(decision, moved, obs.data['url'], rt.desktop, None)
    rt.tick()
    assert action.call_count == 1
    text = (rt.current.runs_dir / 'events.jsonl').read_text()
    assert 'human_confirmation' in text
    assert not (rt.current.runs_dir / 'labels.json').exists()


def test_key_confirmation_rejects_changed_form(rt, monkeypatch):
    decision, target, obs = prepare_key_confirmation(rt, monkeypatch)
    changed = observation(Target('Other button'), url=obs.data['url'])
    monkeypatch.setattr(runtime, 'observe', lambda: changed)
    rt.approved_action_worker(rt.current, 1, rt.step, decision, target, obs.data['url'])
    event = rt.events.get_nowait()
    assert event[0] == 'error'
    assert 'form changed' in event[2]
    assert not rt.desktop.mock_calls


def test_delayed_confirmed_key_action_refreshes_without_repeating_approval(rt, monkeypatch):
    decision, target, obs = prepare_key_confirmation(rt, monkeypatch)
    rt.next_step(rt.current.session_id, rt.step, True)
    rt.tick()
    monkeypatch.setattr(runtime, 'observe', lambda: obs)
    rt.approved_action_worker(rt.current, 1, rt.step, decision, target, obs.data['url'])
    rt.tick()
    assert rt.approved_step == rt.step
    # Voice playback or a slow app delays the already approved action.
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 120.0)
    rt.tick()
    submitted = rt.pool.submit.call_args.args
    assert submitted[0] == rt.approved_action_worker
    assert not rt.requires_confirmation
    fresh = observation(target, captured_at=120.0, url=obs.data['url'])
    monkeypatch.setattr(runtime, 'observe', lambda: fresh)
    submitted[0](*submitted[1:])
    rt.tick()
    action = Mock()
    monkeypatch.setattr(runtime, 'perform', action)
    monkeypatch.setattr(runtime.time, 'monotonic', lambda: 121.0)
    rt.tick()
    action.assert_called_once()
    import json
    events = [json.loads(line) for line in (rt.current.runs_dir / 'events.jsonl').read_text().splitlines()]
    assert sum(item['type'] == 'human_confirmation' for item in events) == 1


def test_guide_key_creation_only_watches_the_humans_click(rt, monkeypatch):
    url = 'https://platform.hcompany.ai/api-keys'
    monkeypatch.setattr(runtime, 'foreground_url', lambda: url)
    target = Target('Create API key')
    decision = CoachDecision(action='click', target=1, speech='Click Create API key when you are ready.')
    rt.accept_decision(1, decision, observation(target, url=url), target)
    assert not rt.requires_confirmation
    assert rt.due is None
    rt.user_input('click', target.center)
    assert rt.due[1] == 'observe'
    assert not rt.desktop.mock_calls


def fake_text_frameworks(monkeypatch, *, ax_result=0):
    import sys
    from hcs_agent import a11y
    class Item:
        def __init__(self, data=None): self.data = data or {}
        @classmethod
        def alloc(cls): return cls()
        def init(self): return self
        def types(self): return list(self.data)
        def dataForType_(self, kind): return self.data[kind]
        def setData_forType_(self, data, kind): self.data[kind] = data
    class Board:
        def __init__(self): self.items = [Item({'text': b'old text', 'image': b'old image'})]; self.count = 0
        def pasteboardItems(self): return self.items
        def clearContents(self): self.items = []; self.count += 1
        def setString_forType_(self, text, kind): self.items = [Item({kind: text.encode()})]; self.count += 1
        def changeCount(self): return self.count
        def writeObjects_(self, items): self.items = items; self.count += 1
    board, values = Board(), {'value': ''}
    setter = Mock(return_value=ax_result)
    AS = SimpleNamespace(AXUIElementCreateApplication=lambda _: 'app', CFEqual=lambda a, b: a == b,
                         AXUIElementSetAttributeValue=setter)
    AppKit = SimpleNamespace(NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: SimpleNamespace(
        frontmostApplication=lambda: SimpleNamespace(processIdentifier=lambda: 1))),
        NSPasteboard=SimpleNamespace(generalPasteboard=lambda: board), NSPasteboardItem=Item,
        NSPasteboardTypeString='text')
    Foundation = SimpleNamespace(NSData=SimpleNamespace(dataWithBytes_length_=lambda data, _: data),
        NSDate=SimpleNamespace(dateWithTimeIntervalSinceNow_=lambda _: None),
        NSRunLoop=SimpleNamespace(currentRunLoop=lambda: SimpleNamespace(runUntilDate_=lambda _: None)))
    monkeypatch.setitem(sys.modules, 'ApplicationServices', AS)
    monkeypatch.setitem(sys.modules, 'AppKit', AppKit)
    monkeypatch.setitem(sys.modules, 'Foundation', Foundation)
    monkeypatch.setattr(a11y, '_attr', lambda ref, attr: 'field' if attr == 'AXFocusedUIElement' else values['value'])
    return board, values, setter


def test_ax_text_write_preserves_unicode_and_multiline_without_clipboard(monkeypatch):
    board, _, setter = fake_text_frameworks(monkeypatch)
    target = Target('Instructions', 'AXTextArea'); target.ref = 'field'
    desktop = Mock()
    text = '# Café\nWait for the user.\nDo not click for them.'
    runtime.set_literal_text(target, text, desktop)
    setter.assert_called_once_with('field', 'AXValue', text)
    assert board.count == 0 and not desktop.mock_calls


def test_paste_fallback_restores_all_clipboard_formats_after_acknowledgment(monkeypatch):
    board, values, _ = fake_text_frameworks(monkeypatch, ax_result=-25205)
    target = Target('Instructions', 'AXTextArea'); target.ref = 'field'
    text = '# Café\nCoach the user.'
    def key(*keys):
        if keys == ('command', 'v'): values['value'] = text
    desktop = Mock(); desktop.hotkey.side_effect = key
    runtime.set_literal_text(target, text, desktop)
    assert board.items[0].data == {'text': b'old text', 'image': b'old image'}
    assert desktop.hotkey.call_count == 2


def test_paste_fallback_does_not_overwrite_a_new_human_copy(monkeypatch):
    board, values, _ = fake_text_frameworks(monkeypatch, ax_result=-25205)
    target = Target('Instructions', 'AXTextArea'); target.ref = 'field'
    text = '# Café\nCoach the user.'
    def key(*keys):
        if keys == ('command', 'v'):
            values['value'] = text
            board.setString_forType_('new human copy', 'text')
    desktop = Mock(); desktop.hotkey.side_effect = key
    runtime.set_literal_text(target, text, desktop)
    assert board.items[0].data == {'text': b'new human copy'}
