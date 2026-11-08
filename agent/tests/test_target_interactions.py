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


def test_wrong_click_does_not_count_but_the_step_stays_armed(rig):
    """Live run 2026-11-08: the user closed a leftover dialog (click elsewhere), then clicked Agents: the old rule
    had dropped the target and the guide waited forever."""
    arm(rig)
    click(rig, (500, 500))
    assert not rig.w.acted("click")
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


def test_ax_control_disappearing_after_target_click_still_requests_verification(rig):
    arm(rig, box=(80, 80, 40, 40))
    click(rig)
    rig.w.update_target_box(None)
    assert rig.w.acted("click")
    assert "Result not verified" in rig.w.observation_note("click")


def test_scroll_drops_an_untracked_point(rig):
    arm(rig)  # pointer only: nothing follows it after a scroll
    click(rig)
    rig.w._on_event("scroll", (100, 100, 0, -1))
    click(rig)
    assert not rig.w.acted("click")


@pytest.mark.parametrize("event,payload", [("scroll", (100, 100, 0, -1)), ("combo_down", None)])
def test_scroll_or_voice_shortcut_resets_evidence_of_a_tracked_box(rig, event, payload):
    arm(rig, box=(80, 80, 40, 40), box_exact=True)
    click(rig)
    rig.w._on_event(event, payload)
    assert not rig.w.acted("click")  # the earlier click no longer counts
    click(rig)
    assert rig.w.acted("click")


def test_browser_navigation_shortcut_resets_evidence_only(rig):
    arm(rig)
    click(rig, settle=False)
    rig.w._on_event("key_down", rig.keys.cmd)
    rig.clock[0] += 0.6
    assert not rig.w.acted("click")
    click(rig)
    assert rig.w.acted("click")


def test_application_change_discards_evidence_and_a_new_click_after_return_counts(rig):
    arm(rig)
    click(rig)
    rig.app[0] = 456
    assert not rig.w.acted("click")
    rig.app[0] = 123
    assert not rig.w.acted("click")  # the click made before the switch does not come back
    click(rig)
    assert rig.w.acted("click")


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
    r.actions.extend([lambda: click(r.rig, (500, 500)), lambda: click(r.rig, (600, 600)), lambda: None])
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


def test_typing_in_a_textarea_counts_after_a_pause_without_enter_or_tab(rig):
    """Live run 2026-11-08: Description field; the user clicked and typed, never pressed Tab: the guide waited forever."""
    arm(rig, kind="type", box=(80, 80, 40, 40), pointer=None)
    rig.w._on_event("click", (100, 100))
    for ch in "Reads a page":
        rig.clock[0] += 0.1
        rig.w._on_event("key_down", SimpleNamespace(char=ch))
    assert not rig.w.acted("type")  # still typing
    rig.clock[0] += cli._InputWatcher.TYPING_IDLE_S
    assert rig.w.acted("type")


def test_typing_then_clicking_next_completes_the_field(rig):
    arm(rig, kind="type", box=(80, 80, 40, 40), pointer=None)
    rig.w._on_event("click", (100, 100))
    rig.w._on_event("key_down", SimpleNamespace(char="x"))
    rig.clock[0] += 0.2
    rig.w._on_event("click", (900, 700))  # Next
    rig.clock[0] += 0.6
    assert rig.w.acted("type")


def test_tracker_sees_a_field_filled_wherever_the_user_clicked(monkeypatch):
    t = cli._TargetTracker() if hasattr(cli, "_TargetTracker") else None
    if t is None:
        t = next(v for v in vars(cli).values() if isinstance(v, type) and hasattr(v, "field_filled"))()
    t.follow(3, "Name *", (454, 528, 604, 20))
    t.initial, t.value, t._fresh = "", "", False
    assert not t.field_filled()
    t.value, t.value_changed_at = "demo-web-reader", 0.0
    assert t.field_filled()
    t.value_changed_at = __import__("time").time()
    assert not t.field_filled()  # still typing


def test_tracker_page_change_is_a_safety_net_for_missed_clicks():
    import time as _t
    t = next(v for v in vars(cli).values() if isinstance(v, type) and hasattr(v, "page_changed"))()
    t.follow(1, "Agents", (100, 360, 40, 30))
    home = ("https://platform.hcompany.ai/", frozenset({("AXLink", "Agents"), ("AXLink", "Sessions")}))
    t.page_initial = t.page_now = home
    t.page_changed_at = 0.0
    assert not t.page_changed()  # nothing moved
    t.page_now = (home[0], home[1] | {("AXButton", "Mark as read")})
    assert not t.page_changed()  # one control appearing (a toast) is not progress
    t.page_now, t.page_changed_at = ("https://platform.hcompany.ai/agents", home[1]), _t.time()
    assert not t.page_changed()  # not settled yet
    t.page_changed_at -= 2
    assert t.page_changed()


@pytest.mark.parametrize("text,is_help", [("And here, what should I do?", True), ("Je fais quoi là ?", True),
                                          ("I'm stuck", True), ("Show me how to create an API key", False),
                                          ("Where is the Billing menu?", False)])
def test_step_questions_do_not_stop_the_task(monkeypatch, text, is_help):
    import queue
    q = queue.Queue()
    q.put(text)
    monkeypatch.setitem(cli._VOICE, "ptt", SimpleNamespace(transcripts=q))
    assert (cli._take_step_question() == text) is is_help
    assert q.empty() is is_help  # a new task stays queued for the router


def test_match_keeps_the_field_content_for_the_tracker():
    from hcs_agent import a11y
    field = a11y.Candidate("AXTextField", "Name *", (454, 528, 604, 20), value="demo-web-reader", required=True)
    best = a11y.match("Name *", [a11y.Candidate("AXStaticText", "Name", (445, 495, 40, 17)), field])[0]
    assert best.name == "Name *" and best.value == "demo-web-reader" and best.required


@pytest.mark.parametrize("text,do_it", [("Create an API key for me and show me", True),
                                        ("Fais-le à ma place : crée une clé API", True),
                                        ("Show me how to create an API key", False),
                                        ("Word. upload them with this session.", False)])
def test_only_an_explicit_do_it_lets_a_spoken_request_act(text, do_it):
    """A mis-transcribed sentence routed as 'act' must never move the mouse; an explicit 'do it for me' may."""
    assert bool(cli._DO_IT.search(text)) is do_it


@pytest.mark.parametrize("q,plan", [("How many agents can I run in parallel?", True),
                                    ("Combien de sessions je peux lancer en même temps ?", True),
                                    ("How much does a session cost?", True), ("What is a skill?", False)])
def test_limit_and_price_questions_point_at_the_plan(q, plan):
    assert bool(cli._PLAN_QUESTION.search(q)) is plan


@pytest.mark.parametrize("text,routed_act,acts", [
    ("Yeah can you build me a napper key?", True, True),   # live 2026-11-08: "an API key" heard as "a napper key"
    ("Can you create an API key?", True, True),
    ("Peux-tu créer une clé API ?", True, True),
    ("Show me how to create an API key", True, False),
    ("Comment je crée une clé API ?", True, False),
    ("Can you create an API key?", False, False),           # router said guide: the Magnet decides
    ("Create an API key for me", False, True),              # explicit "for me" always acts
    ("Word. upload them with this session.", True, False),  # mis-transcription never acts
])
def test_direct_requests_act_how_questions_are_shown(text, routed_act, acts):
    assert cli._wants_it_done(text, routed_act) is acts
