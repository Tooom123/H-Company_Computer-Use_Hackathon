"""Tour navigation contracts, with synthetic AX pages and no physical desktop I/O."""

from dataclasses import dataclass
import queue
import threading
from unittest.mock import Mock

import pytest

from hcs_agent import coach_v2_runtime as runtime
from hcs_agent.coach_v2 import CoachDecision, TourPoint
from hcs_agent.coach_v2_journal import CoachRun


URL = "https://platform.hcompany.ai/agents/sessions"
AGENTS_URL = "https://platform.hcompany.ai/agents"
VIEWPORT = (0, 100, 1440, 900)


@dataclass
class Target:
    name: str = "Agents"
    role: str = "AXButton"
    box: tuple = (24, 250, 210, 40)
    enabled: bool | None = True
    selected: bool | None = None

    @property
    def center(self):
        x, y, width, height = self.box
        return x + width / 2, y + height / 2


def observation(*targets, url=URL, viewport=VIEWPORT, captured_at=100.0):
    targets = targets or (Target(),)
    indexed = dict(enumerate(targets, 1))
    controls = [
        {"id": index, "label": target.name, "role": target.role,
         "box": target.box, "enabled": target.enabled}
        for index, target in indexed.items()
    ]
    return runtime.Observation(
        {"url": url, "title": "H Platform", "controls": controls, "text": []},
        indexed, captured_at, "Chrome", viewport,
    )


@pytest.fixture
def rt(tmp_path, monkeypatch):
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
    obj.current = CoachRun(obj.runs_dir, "Give me a quick tour.", "act")
    obj.history, obj.step, obj.pending, obj.due = [], 0, None, None
    obj.busy = False
    obj.tour = None
    obj.requires_confirmation = obj.confirmation_pending = False
    obj.approved_step = None
    obj.autonomy = 2
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


def test_sidebar_match_ignores_same_label_in_page_content():
    original = Target()
    content = Target(box=(464, 170, 89, 24))
    sidebar = Target()
    fresh = observation(content, sidebar)
    assert runtime.sidebar_target(original, VIEWPORT, fresh) is sidebar


def test_sidebar_match_uses_viewport_relative_geometry_after_window_moves():
    original = Target()
    shifted_viewport = (400, 200, 1440, 900)
    moved = Target(box=(424, 350, 210, 40))
    unrelated = Target(box=(900, 350, 100, 40))
    fresh = observation(unrelated, moved, viewport=shifted_viewport)
    assert runtime.sidebar_target(original, VIEWPORT, fresh) is moved


@pytest.mark.parametrize("targets", [
    (Target(name="Sessions"),),
    (Target(enabled=False),),
    (Target(role="AXHeading"),),
    (Target(box=(500, 250, 210, 40)),),
    (Target(), Target(box=(24, 450, 210, 40))),
])
def test_sidebar_match_refuses_missing_disabled_wrong_role_or_ambiguous(targets):
    assert runtime.sidebar_target(Target(), VIEWPORT, observation(*targets)) is None


@pytest.mark.parametrize("label", ["Create API key", "Run", "Delete", "Upgrade"])
def test_tour_cannot_turn_arbitrary_buttons_into_navigation(label):
    target = Target(name=label)
    assert runtime.sidebar_target(target, VIEWPORT, observation(target)) is None


def test_destination_is_ready_when_sidebar_selection_is_explicit():
    target = Target(selected=True)
    assert runtime.tour_destination_ready(target, observation(target))


def test_destination_is_ready_with_exact_content_heading():
    target = Target()
    heading = Target(role="AXHeading", box=(310, 240, 160, 44))
    assert runtime.tour_destination_ready(target, observation(target, heading))


@pytest.mark.parametrize("heading", [
    Target(name="Sessions", role="AXHeading", box=(310, 240, 160, 44)),
    Target(name="Your Agents", role="AXHeading", box=(310, 240, 160, 44)),
    Target(role="AXStaticText", box=(310, 240, 160, 44)),
    Target(role="AXHeading", box=(24, 240, 160, 44)),
])
def test_destination_does_not_treat_label_mentions_as_page_confirmation(heading):
    target = Target(selected=False)
    assert not runtime.tour_destination_ready(target, observation(target, heading))


def test_act_worker_only_prepares_fresh_target_without_click_or_model(rt, monkeypatch):
    original = Target()
    moved = Target(box=(24, 270, 210, 40))
    fresh = observation(moved)
    point = TourPoint(target=1, speech="Agents is where you configure your assistants.")
    monkeypatch.setattr(runtime, "observe", lambda: fresh)
    model = Mock()
    monkeypatch.setattr(runtime, "CoachClient", model)
    rt.tour_worker(rt.current, 1, point, original, URL,
                   visit=True, viewport=VIEWPORT, index=0)
    assert rt.events.get_nowait() == ("tour_ready", 1, 0, point, fresh, moved)
    assert not rt.desktop.mock_calls
    model.assert_not_called()


def test_cancelled_act_worker_cannot_enqueue_a_new_navigation(rt, monkeypatch):
    original = Target()
    point = TourPoint(target=1, speech="Here are your agents.")

    def cancelled_observation():
        rt.cancel("A new voice request interrupted this tour.")
        return observation(original)

    monkeypatch.setattr(runtime, "observe", cancelled_observation)
    rt.tour_worker(rt.current, 1, point, original, URL,
                   visit=True, viewport=VIEWPORT, index=0)
    assert [event[0] for event in rt.events.queue] == ["cancel"]
    assert not rt.desktop.mock_calls


def test_act_worker_refuses_unexpected_page_change_before_navigation(rt, monkeypatch):
    original = Target()
    point = TourPoint(target=1, speech="Here are your agents.")
    monkeypatch.setattr(runtime, "observe", lambda: observation(original, url=AGENTS_URL))
    rt.tour_worker(rt.current, 1, point, original, URL,
                   visit=True, viewport=VIEWPORT, index=0)
    assert rt.events.get_nowait()[0] == "error"
    assert not rt.desktop.mock_calls


def prepare_tour(rt, *targets):
    targets = targets or (Target(),)
    points = [TourPoint(target=index, speech=f"Here is the {target.name} section.")
              for index, target in enumerate(targets, 1)]
    decision = CoachDecision(action="tour", speech="Let me show you around.", points=points)
    rt.accept_decision(1, decision, observation(*targets), None)
    return points


def run_submitted_worker(rt):
    call = rt.pool.submit.call_args
    function, *args = call.args
    return function(*args, **call.kwargs)


def start_point(rt, monkeypatch, fresh, *, now=101.0):
    monkeypatch.setattr(runtime.time, "monotonic", lambda: now)
    monkeypatch.setattr(runtime, "observe", lambda: fresh)
    rt.tick()
    assert rt.pool.submit.call_args.args[0] == rt.tour_worker
    run_submitted_worker(rt)


@pytest.mark.parametrize("destination_url", [AGENTS_URL, URL])
def test_act_clicks_only_after_fresh_preparation_and_narrates_after_arrival(rt, monkeypatch, destination_url):
    target = Target()
    points = prepare_tour(rt, target)
    perform = Mock()
    model = Mock()
    monkeypatch.setattr(runtime, "perform", perform)
    monkeypatch.setattr(runtime, "CoachClient", model)
    fresh = observation(target, captured_at=101.0)
    start_point(rt, monkeypatch, fresh)
    perform.assert_not_called()  # the preparation worker cannot touch the desktop
    assert rt.show.call_count == 1  # introduction, not the page description yet

    rt.tick()
    perform.assert_called_once()
    assert perform.call_args.args[1] is target
    assert rt.tour["phase"] == "navigating" and rt.tour["index"] == 0
    assert rt.due[1] == "tour_arrival"
    assert rt.show.call_count == 1

    heading = Target(role="AXHeading", box=(310, 240, 160, 44))
    destination = observation(target, heading, url=destination_url, captured_at=101.2)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 101.2)
    monkeypatch.setattr(runtime, "foreground_url", lambda: destination_url)
    monkeypatch.setattr(runtime, "observe", lambda: destination)
    rt.tick()
    assert rt.pool.submit.call_args.args[0] == rt.arrival_worker
    run_submitted_worker(rt)
    rt.tick()
    assert rt.tour["phase"] == "presenting" and rt.tour["index"] == 1
    assert rt.tour["url"] == destination_url
    rt.show.assert_called_with(points[0].speech, target)
    assert perform.call_count == 1
    model.assert_not_called()


def test_act_already_selected_section_is_presented_without_redundant_click(rt, monkeypatch):
    target = Target(name="Sessions", selected=True)
    points = prepare_tour(rt, target)
    perform = Mock()
    monkeypatch.setattr(runtime, "perform", perform)
    start_point(rt, monkeypatch, observation(target, captured_at=101.0))
    rt.tick()
    perform.assert_not_called()
    assert rt.tour["index"] == 1 and rt.tour["phase"] == "presenting"
    rt.show.assert_called_with(points[0].speech, target)


def test_act_waits_for_intro_voice_before_preparing_a_click(rt, monkeypatch):
    prepare_tour(rt)
    rt.speaker.speaking = True
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 101.0)
    rt.tick()
    rt.pool.submit.assert_not_called()
    assert not rt.desktop.mock_calls
    rt.speaker.speaking = False
    rt.tick()
    rt.pool.submit.assert_called_once()


@pytest.mark.parametrize("foreground", ["", "https://example.com/", AGENTS_URL])
def test_foreground_change_after_worker_preparation_prevents_click(rt, monkeypatch, foreground):
    prepare_tour(rt)
    perform = Mock()
    monkeypatch.setattr(runtime, "perform", perform)
    start_point(rt, monkeypatch, observation(captured_at=101.0))
    monkeypatch.setattr(runtime, "foreground_url", lambda: foreground)
    rt.tick()
    perform.assert_not_called()
    assert rt.current.state.value == "blocked"


def test_stop_after_preparation_queue_prevents_any_click(rt, monkeypatch):
    prepare_tour(rt)
    perform = Mock()
    monkeypatch.setattr(runtime, "perform", perform)
    start_point(rt, monkeypatch, observation(captured_at=101.0))
    rt.cancel("The user stopped this tour.")
    rt.tick()
    perform.assert_not_called()
    assert rt.current.state.value == "stopped"
    assert rt.tour is None and rt.due is None


def test_duplicate_ready_event_cannot_click_twice(rt, monkeypatch):
    prepare_tour(rt)
    perform = Mock()
    monkeypatch.setattr(runtime, "perform", perform)
    start_point(rt, monkeypatch, observation(captured_at=101.0))
    ready = rt.events.queue[0]
    rt.events.put(ready)
    rt.tick()
    perform.assert_called_once()
    assert rt.tour["phase"] == "navigating"


def test_stale_preparation_is_not_clicked(rt, monkeypatch):
    prepare_tour(rt)
    perform = Mock()
    monkeypatch.setattr(runtime, "perform", perform)
    start_point(rt, monkeypatch, observation(captured_at=95.0))
    rt.tick()
    perform.assert_not_called()
    assert rt.current.state.value == "blocked"


def navigation_payload(rt, monkeypatch):
    prepare_tour(rt)
    monkeypatch.setattr(runtime, "perform", Mock())
    start_point(rt, monkeypatch, observation(captured_at=101.0))
    rt.tick()
    return rt.due[2]


def test_arrival_rechecks_page_without_reclicking_when_not_ready(rt, monkeypatch):
    payload = navigation_payload(rt, monkeypatch)
    fresh = observation(captured_at=101.0)
    monkeypatch.setattr(runtime, "observe", lambda: fresh)
    rt.arrival_worker(rt.current, 1, payload)
    rt.tick()
    assert rt.tour["phase"] == "navigating" and rt.tour["index"] == 0
    assert rt.due[1] == "tour_arrival"
    assert rt.show.call_count == 1  # no destination explanation before verification
    runtime.perform.assert_called_once()


def test_arrival_timeout_stops_without_claiming_tour_success(rt, monkeypatch):
    payload = navigation_payload(rt, monkeypatch)
    now = payload["deadline"] + .1
    monkeypatch.setattr(runtime.time, "monotonic", lambda: now)
    monkeypatch.setattr(runtime, "observe", lambda: observation(captured_at=now))
    rt.arrival_worker(rt.current, 1, payload)
    rt.tick()
    assert rt.current.state.value == "blocked"
    assert not rt.current.report["verification"]["satisfied"]
    assert rt.tour is None and rt.due is None
    runtime.perform.assert_called_once()


@pytest.mark.parametrize("url", [
    "https://hub.hcompany.ai/agents-api/overview",
    "https://platform.hcompany.ai.evil.example/agents",
    "http://platform.hcompany.ai/agents",
    "https://platform.hcompany.ai:8443/agents",
])
def test_arrival_cannot_accept_another_origin_even_with_expected_heading(rt, monkeypatch, url):
    payload = navigation_payload(rt, monkeypatch)
    target = Target(selected=True)
    monkeypatch.setattr(runtime, "observe", lambda: observation(target, url=url))
    rt.arrival_worker(rt.current, 1, payload)
    assert rt.events.get_nowait()[0] == "error"


def test_cancelled_arrival_cannot_present_stale_guidance(rt, monkeypatch):
    payload = navigation_payload(rt, monkeypatch)
    fresh = observation(Target(selected=True), url=AGENTS_URL, captured_at=101.0)
    monkeypatch.setattr(runtime, "observe", lambda: fresh)
    rt.arrival_worker(rt.current, 1, payload)
    rt.cancel("A new request interrupted the tour.")
    rt.tick()
    assert rt.current.state.value == "stopped"
    assert rt.show.call_count == 1
    assert rt.tour is None and rt.due is None
    runtime.perform.assert_called_once()


def test_three_page_tour_navigates_sequentially_with_no_further_model_requests(rt, monkeypatch):
    targets = [Target(name=name, box=(24, 250 + index * 50, 210, 40))
               for index, name in enumerate(("Agents", "Sessions", "Skills"))]
    points = prepare_tour(rt, *targets)
    clock = [100.0]
    page_url = [URL]
    page = [observation(*targets)]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runtime, "foreground_url", lambda: page_url[0])
    monkeypatch.setattr(runtime, "observe", lambda: page[0])
    perform, model = Mock(), Mock()
    monkeypatch.setattr(runtime, "perform", perform)
    monkeypatch.setattr(runtime, "CoachClient", model)

    for index, (target, point) in enumerate(zip(targets, points)):
        clock[0] += 1
        page[0] = observation(*targets, url=page_url[0], captured_at=clock[0])
        rt.tick()
        assert rt.pool.submit.call_args.args[0] == rt.tour_worker
        run_submitted_worker(rt)
        rt.tick()
        assert perform.call_count == index + 1
        assert perform.call_args.args[1].name == target.name
        assert rt.tour["index"] == index

        clock[0] += .2
        page_url[0] = f"https://platform.hcompany.ai/agents/{target.name.lower()}"
        heading = Target(name=target.name, role="AXHeading", box=(310, 240, 160, 44))
        page[0] = observation(*targets, heading, url=page_url[0], captured_at=clock[0])
        rt.tick()
        assert rt.pool.submit.call_args.args[0] == rt.arrival_worker
        run_submitted_worker(rt)
        rt.tick()
        assert rt.tour["index"] == index + 1
        assert rt.tour["url"] == page_url[0]
        rt.show.assert_called_with(point.speech, target)

    clock[0] += 1
    rt.tick()
    assert rt.current.state.value == "completed"
    assert rt.show.call_count == 4  # introduction + three descriptions; no spoken recap
    assert not rt.current.report["verification"]["satisfied"]
    assert not (rt.current.runs_dir / "labels.json").exists()
    model.assert_not_called()
    assert perform.call_count == 3


def test_guide_tour_keeps_highlights_without_automatic_navigation(rt, monkeypatch):
    rt.current = CoachRun(rt.runs_dir, "Give me a quick tour.", "guide")
    rt.autonomy = 0
    point = prepare_tour(rt)[0]
    target = Target()
    fresh = observation(target, captured_at=101.0)
    perform = Mock()
    monkeypatch.setattr(runtime, "perform", perform)
    start_point(rt, monkeypatch, fresh)
    assert rt.events.queue[0][0] == "tour_point"
    rt.tick()
    rt.show.assert_called_with(point.speech, target)
    assert rt.tour["index"] == 1
    perform.assert_not_called()
