"""GUIDE observations are target-bound evidence, never task-success labels.

Pure fakes: no input listeners, UI, screen capture, microphone, or H calls.
"""

import io
import threading
from types import SimpleNamespace

import pytest

from hcs_agent import cli
from hcs_agent.contract import GuidanceStep, State


class Hub:
    def __init__(self):
        self.subscribers = []

    def subscribe(self, callback):
        self.subscribers.append(callback)

    def unsubscribe(self, callback):
        self.subscribers.remove(callback)


@pytest.fixture
def rig(monkeypatch):
    keys = SimpleNamespace(**{name: object() for name in (
        "enter", "tab", "esc", "space", "backspace", "cmd", "ctrl", "page_down", "shift")})
    clock, app, hub = [100.0], [123], Hub()
    monkeypatch.setitem(cli._MAGNET, "widget", None)
    watcher = cli._InputWatcher(hub=hub, keyboard=SimpleNamespace(Key=keys),
                                clock=lambda: clock[0], focus_probe=lambda: app[0])
    return SimpleNamespace(w=watcher, clock=clock, app=app, hub=hub, keys=keys)


def arm(rig, **kwargs):
    rig.w.arm(SimpleNamespace(**{"box": None, "pointer": (100, 100), **kwargs}))
    rig.clock[0] += 1


def click(rig, xy=(100, 100), *, settle=True):
    rig.w._on_event("click", xy)
    if settle:
        rig.clock[0] += 0.6


def test_target_click_is_settled_observation_with_position_not_success(rig):
    arm(rig)
    click(rig, settle=False)
    assert not rig.w.acted("click")
    rig.clock[0] += 0.6
    assert rig.w.acted("click")
    assert rig.w.last_click_xy == (100, 100)
    note = rig.w.observation_note("click")
    assert note.startswith("Observed interaction:")
    assert "Result not verified" in note and "(100, 100)" in note


def test_reveal_click_is_ignored_before_grace_period(rig):
    rig.w.arm(SimpleNamespace(box=None, pointer=(100, 100)))
    click(rig)
    assert not rig.w.acted("click")
    click(rig)
    assert rig.w.acted("click")


@pytest.mark.parametrize("point,expected", [((128, 100), True), ((129, 100), False), ((128, 128), False)])
def test_pointer_uses_bounded_circular_tolerance(rig, point, expected):
    arm(rig)
    click(rig, point)
    assert rig.w.acted("click") is expected


@pytest.mark.parametrize("point,expected", [((92, 150), True), ((91, 150), False), ((208, 150), True),
                                            ((209, 150), False), ((300, 300), False)])
def test_box_and_margin_take_precedence_over_pointer(rig, point, expected):
    arm(rig, box=(100, 100, 100, 100), pointer=(300, 300))
    click(rig, point)
    assert rig.w.acted("click") is expected


@pytest.mark.parametrize("point", [(None, 10), (float("nan"), 100), (True, 100), (100,), "100,100"])
def test_invalid_event_coordinates_cannot_advance(rig, point):
    arm(rig)
    click(rig, point)
    assert not rig.w.acted("click")


@pytest.mark.parametrize("kind", ["click", "type", "key", "info", "wait"])
def test_missing_target_needs_explicit_confirmation(rig, kind):
    arm(rig, pointer=None, box=None)
    click(rig)
    rig.w._on_event("key_down", SimpleNamespace(char="x"))
    rig.w._on_event("key_down", rig.keys.enter)
    rig.clock[0] += 2
    assert not rig.w.acted(kind)


@pytest.mark.parametrize("kind", ["key", "info", "wait"])
def test_non_click_instructions_are_not_completed_by_a_target_click(rig, kind):
    arm(rig)
    click(rig)
    assert not rig.w.acted(kind)


def test_wrong_click_invalidates_old_coordinates_even_if_next_click_hits(rig):
    arm(rig)
    click(rig, (500, 500))
    click(rig)
    assert not rig.w.acted("click")
    arm(rig)
    click(rig)
    assert rig.w.acted("click")


def test_ax_box_follows_layout_but_does_not_resurrect_invalidated_coordinates(rig):
    arm(rig, box=(80, 80, 40, 40))
    rig.w.update_target_box((280, 80, 40, 40))
    click(rig, (300, 100))
    assert rig.w.acted("click")
    rig.w._on_event("scroll", (0, 0, 0, 1))
    rig.w.update_target_box((280, 80, 40, 40))
    click(rig, (300, 100))
    assert not rig.w.acted("click")


def test_fresh_ax_after_invalidation_can_request_replan_but_never_restore_click_target(rig):
    arm(rig, box=(80, 80, 40, 40))
    rig.w.update_target_box(None)
    rig.clock[0] += 0.2
    measured_at = rig.clock[0]
    measurement = (1, measured_at, 123, (80, 80, 40, 40))
    rig.w.update_target_box(measurement[3])
    click(rig)
    assert not rig.w.acted("click")
    assert rig.w.reobservation_ready(measurement, 1)
    assert rig.w._target is None


@pytest.mark.parametrize("failure", ["predates", "stale", "wrong_step", "wrong_app", "focus_changed",
                                      "missing_box", "unknown_app"])
def test_replan_requires_fresh_same_step_and_same_app_ax_measurement(rig, failure):
    arm(rig, box=(80, 80, 40, 40))
    rig.w.update_target_box(None)
    rig.clock[0] += 0.2
    step, started_at, app, box = 1, rig.clock[0], 123, (80, 80, 40, 40)
    if failure == "predates":
        started_at = rig.w.invalidated_at
    elif failure == "stale":
        rig.clock[0] += 2
    elif failure == "wrong_step":
        step = 2
    elif failure == "wrong_app":
        app = 456
    elif failure == "focus_changed":
        rig.app[0] = 456
    elif failure == "missing_box":
        box = None
    elif failure == "unknown_app":
        rig.w._expected_app = None
    assert not rig.w.reobservation_ready((step, started_at, app, box), 1)


def test_uninvalidated_target_never_requests_automatic_replan(rig):
    arm(rig, box=(80, 80, 40, 40))
    assert not rig.w.reobservation_ready((1, rig.clock[0], 123, (80, 80, 40, 40)), 1)


def test_tracker_does_not_read_ax_when_a_different_app_is_foreground(monkeypatch):
    from hcs_agent import a11y
    monkeypatch.setattr(a11y, "available", lambda: True)
    monkeypatch.setattr(a11y, "find", lambda _: pytest.fail("Must not inspect another app"))
    monkeypatch.setattr(cli._InputWatcher, "_frontmost_app", staticmethod(lambda: 456))
    tracker = cli._TargetTracker()
    tracker.description, tracker.step, tracker.box = "Current plan", 1, (80, 80, 40, 40)
    tracker._expected_app = 123
    waits = iter([False, True])
    tracker._stop = SimpleNamespace(wait=lambda _: next(waits))
    tracker._run()
    assert tracker.box is None and tracker.measurement is None


def test_ax_control_disappearing_after_target_click_still_requests_verification(rig):
    arm(rig, box=(80, 80, 40, 40))
    click(rig)
    rig.w.update_target_box(None)
    assert rig.w.acted("click")
    assert "Result not verified" in rig.w.observation_note("click")


@pytest.mark.parametrize("event,payload", [("scroll", (100, 100, 0, -1)), ("combo_down", None)])
def test_scroll_or_voice_shortcut_invalidates_old_target(rig, event, payload):
    arm(rig)
    click(rig)
    rig.w._on_event(event, payload)
    click(rig)
    assert not rig.w.acted("click")


def test_browser_navigation_shortcut_invalidates_target(rig):
    arm(rig)
    rig.w._on_event("key_down", rig.keys.cmd)
    click(rig)
    assert not rig.w.acted("click")


def test_application_change_invalidates_target_and_return_cannot_resurrect_it(rig):
    arm(rig)
    click(rig)
    rig.app[0] = 456
    assert not rig.w.acted("click")
    rig.app[0] = 123
    click(rig)
    assert not rig.w.acted("click")


def test_click_in_other_application_does_not_count_before_next_poll(rig):
    arm(rig)
    rig.app[0] = 456
    click(rig)
    rig.app[0] = 123
    assert not rig.w.acted("click")


@pytest.mark.parametrize("submit", ["enter", "tab"])
def test_typing_requires_field_click_text_and_explicit_submission(rig, submit):
    arm(rig, box=(80, 80, 100, 40), kind="type")
    rig.w._on_event("key_down", SimpleNamespace(char="a"))
    rig.w._on_event("key_down", rig.keys.enter)
    assert not rig.w.acted("type")
    arm(rig, box=(80, 80, 100, 40), kind="type")
    click(rig)
    rig.w._on_event("key_down", getattr(rig.keys, submit))
    rig.clock[0] += 1
    assert not rig.w.acted("type")  # field click plus Enter alone is insufficient
    rig.w._on_event("key_down", SimpleNamespace(char="SECRET_TEXT"))
    assert not rig.w.acted("type")
    rig.w._on_event("key_down", getattr(rig.keys, submit))
    assert not rig.w.acted("type")
    rig.clock[0] += 0.6
    assert rig.w.acted("type")
    assert "SECRET_TEXT" not in rig.w.observation_note("type")


def test_magnet_controls_are_excluded_and_stop_unsubscribes(rig, monkeypatch):
    monkeypatch.setitem(cli._MAGNET, "widget", SimpleNamespace(contains=lambda x, y: x == 100))
    arm(rig)
    click(rig)
    assert not rig.w.acted("click")
    assert len(rig.hub.subscribers) == 1
    rig.w.stop()
    assert rig.hub.subscribers == []


def intervention(*, terminal_on_next=True):
    it = SimpleNamespace(request=SimpleNamespace(session_id="session-a"), state=State.awaiting_user,
                         guidance=[GuidanceStep(index=1, instruction="Click the named button", pointer=(100, 100),
                                                prepared_speech=["Next candidate only"])],
                         report=None, _thread=None, _user_event=threading.Event(), replies=[], stops=[])

    def next_(command):
        it.replies.append(command)
        it._user_event.set()
        if terminal_on_next:
            it.state, it.report = State.resolved, object()

    def stop(command):
        it.stops.append(command)
        it.state, it.report = State.stopped, object()

    it.next, it.stop = next_, stop
    return it


@pytest.fixture
def loop_rig(rig, monkeypatch):
    import select
    it = intervention()
    prefetched, stopped = [], []
    monkeypatch.setattr(cli, "_InputWatcher", lambda: rig.w)
    monkeypatch.setattr(cli, "_ScreenWatcher", lambda: pytest.fail("Screen differences must not advance GUIDE"))
    monkeypatch.setattr(cli, "_new_request_pending", lambda: False)
    monkeypatch.setitem(cli._SPEECH, "speaker", SimpleNamespace(
        prefetch=lambda texts, **options: prefetched.append((texts, options)), stop=lambda: stopped.append(True)))
    monkeypatch.setattr(select, "select", lambda *args: ([], [], []))
    actions = []
    calls = [0]

    def wait(_):
        calls[0] += 1
        assert calls[0] < 10, "Test loop must terminate"
        rig.clock[0] += 1
        if actions:
            actions.pop(0)()
        elif not it.state.terminal:
            it.state, it.report = State.resolved, object()

    it.wait = wait
    return SimpleNamespace(rig=rig, it=it, actions=actions, prefetched=prefetched, stopped=stopped)


def test_loop_does_not_advance_on_irrelevant_clicks_and_prefetches_once(loop_rig):
    r = loop_rig
    r.actions.extend([lambda: click(r.rig, (500, 500)), lambda: click(r.rig), lambda: None])
    cli._guide_loop(r.it, auto=False, overlay=False)
    assert r.it.replies == []
    assert r.prefetched == [(["Next candidate only"], {"replace": True})]
    assert r.rig.hub.subscribers == []


def test_loop_target_interaction_requests_reobservation_not_claimed_success(loop_rig):
    r = loop_rig
    r.actions.append(lambda: click(r.rig))
    cli._guide_loop(r.it, auto=False, overlay=False)
    assert len(r.it.replies) == 1
    assert r.it.replies[0].note.startswith("Observed interaction:")
    assert "Result not verified" in r.it.replies[0].note


def test_loop_replans_once_from_fresh_ax_without_confirming_action(loop_rig, monkeypatch):
    r = loop_rig
    monkeypatch.setenv("HCS_AX_NATIVE_BUNDLE_ID", "com.exafunction.windsurf")
    r.it.request.software, r.it.request.autonomy, r.it.request.mode = "cognition", 0, cli.Mode.guide
    tracker = SimpleNamespace(measurement=None)

    def follow(step, description, box, **kwargs):
        tracker.measurement = None
        assert kwargs["expected_app"] == 123

    tracker.follow, tracker.stop = follow, lambda: None
    monkeypatch.setattr(cli, "_TargetTracker", lambda: tracker)

    def invalidate_then_measure():
        r.rig.w._on_event("scroll", (0, 0, 0, 1))
        r.rig.clock[0] += 0.2
        tracker.measurement = (r.it.guidance[-1].index, r.rig.clock[0], 123, (80, 80, 40, 40))

    def next_(command):
        r.it.replies.append(command)
        r.it.guidance.append(GuidanceStep(index=2, instruction="Use the freshly observed target",
                                          pointer=(100, 100)))

    r.it.next = next_
    r.actions.extend([invalidate_then_measure, lambda: None, invalidate_then_measure, lambda: None])
    cli._guide_loop(r.it, auto=False, overlay=False)
    assert len(r.it.replies) == 1  # a second invalidation needs explicit confirmation or Stop
    reply = r.it.replies[0]
    assert reply.done is False
    assert reply.note.startswith("Observation only: target invalidated; reobserve requested.")
    assert "No user action was confirmed" in reply.note
    assert r.rig.w._target is None


@pytest.mark.parametrize("software,autonomy,mode,bundle", [
    ("odoo", 0, cli.Mode.guide, "com.exafunction.windsurf"),
    ("cognition", 1, cli.Mode.guide, "com.exafunction.windsurf"),
    ("cognition", 0, cli.Mode.act, "com.exafunction.windsurf"),
    ("cognition", 0, cli.Mode.guide, ""),
    ("cognition", 0, cli.Mode.guide, "other.native.app"),
])
def test_other_modes_keep_explicit_confirmation_without_automatic_replan(
        loop_rig, monkeypatch, software, autonomy, mode, bundle):
    r = loop_rig
    monkeypatch.setenv("HCS_AX_NATIVE_BUNDLE_ID", bundle)
    r.it.request.software, r.it.request.autonomy, r.it.request.mode = software, autonomy, mode
    monkeypatch.setattr(r.rig.w, "reobservation_ready", lambda *args: pytest.fail("Replan is outside this pilot"))
    r.actions.append(lambda: r.rig.w._on_event("scroll", (0, 0, 0, 1)))
    cli._guide_loop(r.it, auto=False, overlay=False)
    assert r.it.replies == []


@pytest.mark.parametrize("stdin,expected", [("", 0), ("\n", 1)])
def test_loop_eof_is_not_explicit_enter(loop_rig, monkeypatch, stdin, expected):
    import select
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(stdin))
    monkeypatch.setattr(select, "select", lambda *args: ([cli.sys.stdin], [], []))
    cli._guide_loop(loop_rig.it, auto=False, overlay=False)
    assert len(loop_rig.it.replies) == expected
    if expected:
        assert "User explicitly requested" in loop_rig.it.replies[0].note


def test_new_voice_request_stops_before_any_guidance_or_prefetch(loop_rig, monkeypatch):
    monkeypatch.setattr(cli, "_new_request_pending", lambda: True)
    cli._guide_loop(loop_rig.it, auto=False, overlay=False)
    assert len(loop_rig.it.stops) == 1 and loop_rig.it.replies == []
    assert loop_rig.prefetched == [] and loop_rig.stopped == [True]


def test_test_mode_does_not_fabricate_human_confirmation(loop_rig, monkeypatch):
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    cli._guide_loop(loop_rig.it, auto=True, overlay=False)
    note = loop_rig.it.replies[0].note
    assert note.startswith("Observed interaction:") and "no human action observed" in note


@pytest.fixture
def control_rig(monkeypatch):
    it = intervention(terminal_on_next=False)
    monkeypatch.setitem(cli._MAGNET, "current", it)
    monkeypatch.setitem(cli._SPEECH, "speaker", None)
    return it


@pytest.mark.parametrize("done", [True, False])
def test_desktop_confirmation_is_explicit_bound_and_single_use(control_rig, done):
    assert cli._control_next("session-a", 1, done)
    assert not cli._control_next("session-a", 1, done)
    reply = control_rig.replies[0]
    assert reply.done is done and "User explicitly reported" in reply.note
    assert "result not verified" in reply.note
    assert len(control_rig.replies) == 1


@pytest.mark.parametrize("session,step,done", [("other", 1, True), ("session-a", 2, True),
                                              ("session-a", True, True), ("session-a", 1, "yes")])
def test_stale_or_invalid_desktop_confirmation_is_rejected(control_rig, session, step, done):
    assert not cli._control_next(session, step, done)
    assert control_rig.replies == []


def test_stopped_intervention_rejects_desktop_confirmation(control_rig):
    control_rig.state = State.stopping
    assert not cli._control_next("session-a", 1, True)
    assert control_rig.replies == []


def test_stop_winning_race_is_not_a_confirmation(control_rig):
    def stopped(_):
        raise RuntimeError("Cannot continue in state stopping")
    control_rig.next = stopped
    assert not cli._control_next("session-a", 1, True)


@pytest.mark.parametrize("next_state", [State.awaiting_user, State.running])
def test_desktop_next_clears_old_marker_on_ui_tick_even_if_worker_already_woke(loop_rig, monkeypatch, next_state):
    import sys
    r = loop_rig
    monkeypatch.setitem(sys.modules, "hcs_agent.overlay", SimpleNamespace(Scene=SimpleNamespace, Mark=SimpleNamespace))
    monkeypatch.setattr(cli, "_say", lambda *args: None)
    monkeypatch.setitem(cli._MAGNET, "current", r.it)
    hides, scenes = [], []

    def next_(command):
        r.it.replies.append(command)
        r.it._user_event.set()
        r.it.state = next_state

    def run_until(finished, tick, interval):
        tick()
        assert len(scenes) == 1 and hides == []
        assert cli._control_next("session-a", 1, True)
        assert hides == []  # HTTP callback must not touch AppKit
        tick()
        assert hides == [True]
        tick()
        assert hides == [True]  # don't erase unrelated later narration on every poll
        r.it.state, r.it.report = State.resolved, object()

    r.it.next = next_
    overlay = SimpleNamespace(hold_reveal=lambda: False, badge=lambda *args, **kwargs: None,
                              hide=lambda: hides.append(True), show_scene=scenes.append, run_until=run_until)
    cli._guide_loop(r.it, auto=False, overlay=True, ov=overlay)
    assert len(r.it.replies) == 1


def test_input_hub_forwards_scroll_without_another_listener(monkeypatch):
    import sys
    from hcs_agent.inputs import InputHub
    listeners = []

    class Listener:
        def __init__(self, **callbacks):
            self.callbacks = callbacks
            listeners.append(self)

        def start(self):
            pass

    monkeypatch.setitem(sys.modules, "pynput", SimpleNamespace(
        mouse=SimpleNamespace(Listener=Listener), keyboard=SimpleNamespace(Listener=Listener)))
    hub = InputHub()
    events = []
    hub.subscribe(lambda *args: events.append(args))
    listeners[0].callbacks["on_scroll"](100, 200, 0, -3)
    assert events == [("scroll", (100, 200, 0, -3))]
    assert len(listeners) == 2  # existing mouse and keyboard listeners only
