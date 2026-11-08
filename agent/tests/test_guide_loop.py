"""Regression: live run 2026-11-08, "create an agent". The wizard opened, Build vanished from the visible controls,
and the planner said "Click 'Build ⌘B'" while framing Close: open, close, open... four times."""

from types import SimpleNamespace

import pytest

from hcs_agent import cli
from hcs_agent.backend import MockBackend
from hcs_agent.procedures import ProcedureRegistry
from hcs_agent.runner import Intervention, _label_matches, _page_change_note, _quoted_labels


def ctl(role, name, x=100):
    return SimpleNamespace(role=role, name=name, center=(x, 100), box=(x - 20, 80, 40, 40))


AGENTS = [ctl("AXLink", "Agents", 50), ctl("AXButton", "Build ⌘B", 1400)]
WIZARD = [ctl("AXLink", "Agents", 50), ctl("AXHeading", "Build an agent", 700), ctl("AXButton", "Close", 1060),
          ctl("AXTextField", "Name", 700)]


@pytest.fixture
def guide(tmp_path, monkeypatch):
    req = cli._coaching_request("Show me how to create an agent.", "hcompany", "")
    backend = MockBackend()
    it = Intervention(req, backend, ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    bound = ProcedureRegistry().for_request(req).bound(req)
    page = SimpleNamespace(items=WIZARD)
    info = SimpleNamespace(is_front=True, title="H Platform", url="https://platform.hcompany.ai/agents")
    backend.page_catalogue = lambda _: (info, list(page.items))
    shown, calls = [], []
    monkeypatch.setattr(it, "_on_guidance", lambda step: shown.append(step) or (True, None))
    monkeypatch.setattr(it, "_wait_page_change", lambda *a: (info, list(page.items)))
    monkeypatch.setattr("hcs_agent.overlay.screen_size_points", lambda: (1512, 982))
    return SimpleNamespace(it=it, bound=bound, backend=backend, page=page, shown=shown, calls=calls)


def test_instruction_naming_a_missing_control_is_replanned_not_framed_on_another(guide):
    plans = iter([{"done": False, "instruction": "Click the 'Build ⌘B' button in the top right.", "kind": "click", "target": 2},
                  {"done": False, "instruction": "Click the 'Name' field.", "kind": "click", "target": 3},
                  {"done": True, "summary": "ok"}])
    guide.backend.plan_step = lambda *a: guide.calls.append(a) or next(plans)
    guide.it._dynamic_guide(guide.bound)
    assert all(s.where != "Close" for s in guide.shown)
    assert guide.shown[0].where == "Name"
    assert any("not among the listed controls" in h for h in guide.calls[1][4])
    assert any(h.startswith("Screenshot check") for h in guide.calls[1][4])


def test_mismatched_target_is_moved_to_the_named_control(guide):
    guide.page.items = AGENTS
    plans = iter([{"done": False, "instruction": "Click 'Build ⌘B'.", "kind": "click", "target": 0},
                  {"done": True, "summary": "ok"}])
    guide.backend.plan_step = lambda *a: next(plans)
    guide.it._dynamic_guide(guide.bound)
    assert guide.shown[0].where == "Build ⌘B" and guide.shown[0].pointer == (1400, 100)


def test_same_step_across_alternating_pages_is_caught(guide):
    pages = iter([WIZARD, AGENTS] * 10)
    guide.it._wait_page_change = lambda *a: (None, guide.page.__setattr__("items", next(pages)) or guide.page.items)
    guide.page.items = AGENTS
    guide.backend.plan_step = lambda *a: guide.calls.append(a) or {
        "done": False, "instruction": "Click the Build button.", "kind": "click", "target": 0}
    result = guide.it._dynamic_guide(guide.bound, max_steps=6)
    assert result is not None  # never stops mid-task: it keeps guiding
    assert any("already gave the step" in h for c in guide.calls for h in c[4])


def test_history_tells_the_planner_what_the_click_opened(guide):
    guide.page.items = AGENTS
    guide.it._wait_page_change = lambda *a: (None, WIZARD)
    plans = iter([{"done": False, "instruction": "Click 'Build ⌘B'.", "kind": "click", "target": 1},
                  {"done": True, "summary": "ok"}])
    guide.backend.plan_step = lambda *a: guide.calls.append(a) or next(plans)
    guide.it._dynamic_guide(guide.bound)
    note = guide.calls[1][4][-1]
    assert "Heading 'Build an agent'" in note and "Button 'Close'" in note and "no longer visible: Button 'Build ⌘B'" in note


def test_label_helpers():
    assert _quoted_labels("Type \"demo-web-reader\" in the 'Name' field", exclude="demo-web-reader") == ["Name"]
    assert _quoted_labels("Open the agent's settings") == []
    assert _label_matches("Build", "Build ⌘B") and not _label_matches("Build ⌘B", "Close")
    assert _page_change_note(AGENTS, AGENTS) == "Page after that: no visible change within 2 s."


def test_native_catalogue_keeps_navigation_over_timeline_ticks_and_counters(monkeypatch):
    """Devin Desktop probe 2026-11-08: 121 named elements, the walk lists the bottom first, and the 90 cut dropped
    Agents / Expand sidebar / Back while keeping 8 px '5:35 AM' ticks and diff counters."""
    from hcs_agent import a11y
    from hcs_agent.backend import HBackend

    C = lambda role, name, x, y, w=28, h=28: a11y.Candidate(role, name, (x, y, w, h))
    bottom = [C("AXButton", "Send", 1071, 927), C("AXStaticText", "72", 590, 831, 16, 15),
              C("AXStaticText", "+", 541, 831, 8, 15)]
    ticks = [C("AXButton", f"{i}:00 AM", 1469, 100 + 8 * i, 26, 8) for i in range(60)]
    text = [C("AXStaticText", f"message line {i}", 410, 110 + 20 * i, 600, 17) for i in range(40)]
    top = [C("AXPopUpButton", "Agents", 37, 39, 84), C("AXButton", "Expand sidebar", 8, 39)]
    info = a11y.PageInfo(app="Devin Desktop", title="s", url="", is_front=True, native=True,
                         bundle_id="com.exafunction.windsurf", elements=bottom + ticks + text + top)
    monkeypatch.setattr(a11y, "page", lambda: info)
    monkeypatch.setattr(a11y, "visible_at_point", lambda e: True)
    b = HBackend.__new__(HBackend)
    b.use_a11y, b.observe_only = True, True
    _, items = b.page_catalogue()
    names = [e.name for e in items]
    assert names[:2] == ["Expand sidebar", "Agents"] and "Send" in names
    assert not any(n.endswith("AM") for n in names) and "72" not in names and "+" not in names


def test_unscripted_request_survives_braces_in_docs_and_goal():
    """Live crash 2026-11-08: the docs map carried '{ ... : sessionId }' into a generic procedure ->
    ValueError: Invalid format specifier ' sessionId '."""
    from hcs_agent.contract import InterventionRequest, Mode
    from hcs_agent.procedures import make_generic_procedure

    req = InterventionRequest(software="hcompany", goal="Upload files {with} this session", mode=Mode.guide,
                              procedure_id="generic")
    bound = make_generic_procedure(req, 'POST /sessions body: { "files": [...] : sessionId }').bound(req)
    assert '{ "files": [...] : sessionId }' in bound.guide_instructions
    assert "Upload files {with} this session" in bound.objective


def test_click_on_a_heading_is_replanned_with_a_screenshot_check(guide):
    """Live run 2026-11-08: wizard open, the planner said "Click the 'Build an agent' heading to start the wizard"."""
    looked = []
    guide.backend.effect_visible = lambda expected: looked.append(expected) or (
        True, "Chrome, H Platform: the Build an agent wizard is open on Details, with a Name field")
    plans = iter([{"done": False, "instruction": "Click the 'Build an agent' heading to start the wizard.", "kind": "click", "target": 1},
                  {"done": False, "instruction": "Click the 'Name' field.", "kind": "click", "target": 3},
                  {"done": True, "summary": "ok"}])
    guide.backend.plan_step = lambda *a: guide.calls.append(a) or next(plans)
    guide.it._dynamic_guide(guide.bound)
    assert [s.where for s in guide.shown][0] == "Name"
    notes = guide.calls[1][4]
    assert any("not a control" in h for h in notes) and any("wizard is open on Details" in h for h in notes)
    assert len(looked) == 1  # one screenshot, only when unsure


def test_screenshot_check_is_never_taken_by_the_native_pilot(guide, monkeypatch):
    monkeypatch.setenv("HCS_AX_NATIVE_BUNDLE_ID", "com.exafunction.windsurf")
    guide.backend.effect_visible = lambda *a: pytest.fail("native pilot must not capture the desktop")
    assert guide.it._screen_note(["Instruction shown: Click 'Build'. ..."]) is None


def test_scripted_hints_carry_their_done_when(tmp_path, monkeypatch):
    from hcs_agent.contract import InterventionRequest, Mode

    req = InterventionRequest(software="hcompany", goal="Build an agent and run it", mode=Mode.guide,
                              procedure_id="hcompany_platform_run_cloud_session")
    backend = MockBackend()
    it = Intervention(req, backend, ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    seen = {}
    monkeypatch.setattr(it, "_ensure_screen", lambda b: True)
    monkeypatch.setattr(it, "_dynamic_guide", lambda b, hints=None, **k: seen.setdefault("hints", hints) and None)
    it.start(); it.approve(__import__("hcs_agent.contract", fromlist=["ApproveCommand"]).ApproveCommand()); it.wait(3)
    assert any("Build an agent" in h and "[done when:" in h and "name field" in h for h in seen["hints"])


def test_planner_sees_empty_required_fields_and_their_values():
    from hcs_agent.runner import _field_state
    name = SimpleNamespace(value="", required=True)
    desc = SimpleNamespace(value="Reads a page", required=True)
    assert _field_state(name) == " EMPTY REQUIRED"
    assert _field_state(desc) == ' value="Reads a page" REQUIRED'
    assert _field_state(SimpleNamespace(value=None)) == ""  # native pilot: values never read


def test_overlay_keeps_the_dialog_holding_the_target_clear():
    from hcs_agent.runner import _container_of
    dialog = ctl("AXGroup", "Build an agent", 0)
    dialog.frame = dialog.box = (420, 330, 672, 478)
    page = ctl("AXGroup", "Main", 0)
    page.frame = page.box = (0, 0, 1512, 982)
    nxt = ctl("AXButton", "Next", 0)
    nxt.box = (1012, 755, 63, 36)
    assert _container_of(nxt, [page, dialog, nxt], 1512, 982) == [(420, 330, 672, 478)]


def test_a_label_target_is_moved_to_the_field_it_names(guide):
    """Live run 2026-11-08: "Type demo-web-reader in the Name field" framed the label 'Name' above the field,
    so the user's click in the field was outside the frame and the step never completed."""
    label = ctl("AXStaticText", "Name", 465)
    field = ctl("AXTextField", "Name *", 756)
    guide.page.items = [ctl("AXHeading", "Build an agent", 700), label, field, ctl("AXButton", "Next", 1040)]
    plans = iter([{"done": False, "instruction": "Type \"demo-web-reader\" in the Name field.", "kind": "type",
                   "text": "demo-web-reader", "target": 1}, {"done": True, "summary": "ok"}])
    guide.backend.plan_step = lambda *a: next(plans)
    guide.it._dynamic_guide(guide.bound)
    assert guide.shown[0].where == "Name *" and guide.shown[0].pointer == (756, 100) and guide.shown[0].kind == "type"


def test_label_target_finds_a_field_the_hit_test_dropped(guide):
    """Live 2026-11-08: the catalogue had the label 'Name' but not the field 'Name *' (dropped by the
    visibility hit-test): the step was shown without a frame and the guide waited."""
    label = ctl("AXStaticText", "Name", 465)
    field = ctl("AXTextField", "Name *", 560)
    far = ctl("AXTextField", "Name of the vault", 1400)
    guide.page.items = [ctl("AXHeading", "Build an agent", 700), label, ctl("AXButton", "Next", 1040)]
    info = SimpleNamespace(is_front=True, title="H Platform", url="https://platform.hcompany.ai/agents",
                           elements=[*guide.page.items, field, far])
    guide.backend.page_catalogue = lambda _: (info, list(guide.page.items))
    plans = iter([{"done": False, "instruction": "Type \"demo-web-reader\" in the Name field.", "kind": "type",
                   "text": "demo-web-reader", "target": 1}, {"done": True, "summary": "ok"}])
    guide.backend.plan_step = lambda *a: next(plans)
    guide.it._dynamic_guide(guide.bound)
    assert guide.shown[0].where == "Name *" and guide.shown[0].pointer == (560, 100)


def test_every_hcompany_task_gets_the_platform_knowledge(tmp_path, monkeypatch):
    """Not only the two wizard procedures: an unscripted request on the site explains from the same knowledge."""
    from hcs_agent.contract import InterventionRequest, Mode

    req = InterventionRequest(software="hcompany", goal="How do I pause a running session?", mode=Mode.guide,
                              procedure_id="generic")
    backend = MockBackend()
    it = Intervention(req, backend, ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    bound = ProcedureRegistry().for_request(req).bound(req)
    info = SimpleNamespace(is_front=True, title="H Platform", url="https://platform.hcompany.ai/sessions")
    backend.page_catalogue = lambda _: (info, [ctl("AXButton", "Pause", 300)])
    calls = []
    backend.plan_step = lambda *a: calls.append(a) or {"done": True, "summary": "ok"}
    monkeypatch.setattr(it, "_on_guidance", lambda step: (True, None))
    monkeypatch.setattr("hcs_agent.overlay.screen_size_points", lambda: (1512, 982))
    it._dynamic_guide(bound)
    context = calls[0][1]
    assert "Agent View" in context and "Subagents" in context and "pause / resume" in context


def test_step_limit_follows_the_procedure(guide):
    seen = []
    guide.backend.plan_step = lambda *a: seen.append(1) or {"done": False, "instruction": f"Click Next {len(seen)}",
                                                              "kind": "click", "target": 0}
    guide.page.items = [ctl("AXButton", "Next", 1040)]
    guide.it._wait_page_change = lambda *a: None
    guide.it._dynamic_guide(guide.bound)
    assert len(seen) > 14  # the wizard + result page tour no longer cut at 14 steps


@pytest.mark.parametrize("names,step", [
    (["1 Details", "2 Config", "3 Instructions", "4 Skills", "5 Subagents", "6 Session"], "Details"),
    (["Details", "2 Config", "3 Instructions", "4 Skills", "5 Subagents", "6 Session"], "Config"),
    (["Details", "Config", "Instructions", "Skills", "Subagents", "6 Session"], "Session"),
    (["Agents", "Sessions"], None)])
def test_wizard_step_from_the_stepper(names, step):
    """Labels read on the live Build an agent wizard, 2026-11-08: done steps lose their number."""
    from hcs_agent.runner import _wizard_step
    assert _wizard_step([ctl("AXRadioButton", n) for n in names]) == step


def test_planned_page_notes_explain_each_wizard_page_then_the_planner_acts(guide):
    stepper = [ctl("AXRadioButton", n) for n in ["Details", "2 Config", "3 Instructions", "4 Skills", "5 Subagents", "6 Session"]]
    guide.page.items = stepper + [ctl("AXPopUpButton", "Web environment (default)", 600),
                                  ctl("AXPopUpButton", "Platform default (holo4-27b)", 700),
                                  ctl("AXPopUpButton", "Free-form text", 800), ctl("AXButton", "Next", 1040)]
    plans = iter([{"done": False, "instruction": "Click 'Next'.", "kind": "click", "target": len(guide.page.items) - 1},
                  {"done": True, "summary": "ok"}])
    guide.backend.plan_step = lambda *a: guide.calls.append(a) or next(plans)
    guide.it._dynamic_guide(guide.bound, history=["Instruction shown: Click 'Next'. ..."])
    kinds = [(s.kind, s.where) for s in guide.shown]
    assert kinds[:3] == [("info", "Web environment (default)"), ("info", "Platform default (holo4-27b)"),
                         ("info", "Free-form text")]
    assert kinds[3] == ("click", "Next")
    assert any("planned page note" in h for h in guide.calls[0][4])


def test_no_page_tour_before_the_guidance_reached_the_page(guide):
    """A question asked while a session page is open must not start the Agent View tour."""
    guide.page.items = [ctl("AXButton", "Agent action · Step 1 of 1", 700), ctl("AXButton", "Billing", 100)]
    guide.backend.plan_step = lambda *a: {"done": True, "summary": "ok"}
    info = SimpleNamespace(is_front=True, title="H", url="https://platform.hcompany.ai/agents/sessions/x", elements=None)
    guide.backend.page_catalogue = lambda _: (info, list(guide.page.items))
    guide.it._dynamic_guide(guide.bound)
    assert all(s.kind != "info" or s.last for s in guide.shown)


def test_guidance_resumes_when_the_screen_says_the_goal_is_not_reached(tmp_path, monkeypatch):
    """User feedback 2026-11-08: "it stops too early, even if I change page it should notice and bring me back"."""
    from hcs_agent.backend import AttemptResult, VerifyResult
    from hcs_agent.contract import ApproveCommand, CaseStatus, DeclaredResult, InterventionRequest, Mode

    req = InterventionRequest(software="hcompany", goal="Build an agent and run it", mode=Mode.guide,
                              procedure_id="hcompany_platform_run_cloud_session")
    it = Intervention(req, MockBackend(), ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    runs, checks = [], iter([{"session_open": False, "cloud_environment": True},
                             {"session_open": True, "cloud_environment": True}])
    monkeypatch.setattr(it, "_ensure_screen", lambda b: True)
    monkeypatch.setattr(it, "_dynamic_guide", lambda b, hints=None, history=None, **k: runs.append(history) or
                        AttemptResult(None, "completed", DeclaredResult(outcome="done")))
    monkeypatch.setattr(it, "_fast_verify", lambda b: VerifyResult(None, "completed", checks=next(checks),
                                                                   observed="Agents page"))
    it.start(); it.approve(ApproveCommand()); it.wait(5)
    assert len(runs) == 2 and runs[0] is None and "not reached yet" in runs[1][0]
    assert it.report.status is CaseStatus.resolved


def test_docs_question_from_the_platform_is_guided_not_waiting_for_the_docs_site(tmp_path, monkeypatch):
    """Live 2026-11-08: "How to build a skill?" on the platform waited 40 screen checks for hub.hcompany.ai,
    showing "Bring hcompany (CRM pipeline) to the front"."""
    from hcs_agent.contract import ApproveCommand, InterventionRequest, Mode
    from hcs_agent.backend import AttemptResult
    from hcs_agent.contract import DeclaredResult

    req = InterventionRequest(software="hcompany", goal="How to build a skill?", mode=Mode.guide,
                              procedure_id="hcompany_hub_find_documentation",
                              parameters={"topic": "build a skill", "page_title": "Skills"})
    it = Intervention(req, MockBackend(), ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    monkeypatch.setattr(it, "_ensure_screen", lambda b: pytest.fail("must not wait for the expected screen"))
    seen = {}
    monkeypatch.setattr(it, "_dynamic_guide", lambda b, hints=None, history=None, **k: seen.setdefault("hints", hints)
                        and AttemptResult(None, "completed", DeclaredResult(outcome="blocked", summary="x", blocker="x")))
    it.start(); it.approve(ApproveCommand()); it.wait(5)
    assert "hub.hcompany.ai" in seen["hints"][0] and "first guide the person there" in seen["hints"][0]


def test_newcomer_tour_points_at_each_sidebar_section_not_the_breadcrumb():
    """Sidebar and breadcrumb labels read on the live platform, 2026-11-08 ("Agents"/"Sessions" exist in both)."""
    from hcs_agent.runner import _page_notes, _next_page_note
    sidebar = [ctl("AXButton", n, 100) for n in ["Home", "Projects", "Agents", "Sessions", "Skills", "Environments",
                                                 "Browser Profiles", "Vaults", "Schedules", "Organisation",
                                                 "API keys", "Webhooks", "Upgrade"]]
    crumbs = [ctl("AXButton", "Agents", 468), ctl("AXButton", "Sessions", 575)]
    items = crumbs + sidebar + [ctl("AXButton", "Help and feedback", 1464)]
    notes = [n for n in _page_notes("hcompany") if n.get("procedure") == "hcompany_platform_tour"]
    info = SimpleNamespace(url="https://platform.hcompany.ai/", elements=items)
    shown, order = set(), []
    while (r := _next_page_note(notes, shown, info, items)):
        shown.add(r[0]); order.append((r[1].name, r[1].center[0]))
    assert [n for n, _ in order] == ["Agents", "Sessions", "Skills"]  # 20-second tour (demo feedback)
    assert dict(order)["Agents"] == 100 and dict(order)["Sessions"] == 100  # sidebar, not breadcrumb


def test_planned_notes_are_spoken_in_one_short_line(guide):
    """User feedback 2026-11-08: the agent + cloud session flow was right but far too long to listen to."""
    from hcs_agent.runner import _page_notes
    notes = _page_notes("hcompany")
    assert notes and all(n.get("say") and len(n["say"]) <= 90 for n in notes)
    stepper = [ctl("AXRadioButton", n) for n in ["Details", "2 Config", "3 Instructions", "4 Skills", "5 Subagents", "6 Session"]]
    guide.page.items = stepper + [ctl("AXPopUpButton", "Web environment (default)", 600), ctl("AXButton", "Next", 1040)]
    plans = iter([{"done": True, "summary": "ok"}])
    guide.backend.plan_step = lambda *a: next(plans)
    guide.it._dynamic_guide(guide.bound, history=["Instruction shown: Click 'Next'. ..."])
    step = guide.shown[0]
    assert step.why == next(n["say"] for n in notes if n["text"] == step.instruction)
    assert step.prepared_speech == [step.instruction]  # the voice says the title; the line under it is written


def test_tour_ends_after_its_three_notes_without_the_planner(tmp_path, monkeypatch):
    """Demo feedback 2026-11-08: the tour must fit in about 20 seconds and then stop."""
    from hcs_agent.contract import InterventionRequest, Mode

    req = InterventionRequest(software="hcompany", goal="I'm new here, quick tour?", mode=Mode.guide,
                              procedure_id="hcompany_platform_tour")
    backend = MockBackend()
    it = Intervention(req, backend, ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    bound = ProcedureRegistry().for_request(req).bound(req)
    items = [ctl("AXButton", "Agents", 468), ctl("AXButton", "Sessions", 575)] + \
            [ctl("AXButton", n, 100) for n in ["Home", "Agents", "Sessions", "Skills", "Environments"]]
    info = SimpleNamespace(is_front=True, title="H Platform", url="https://platform.hcompany.ai/", elements=items)
    backend.page_catalogue = lambda _: (info, items)
    backend.plan_step = lambda *a: pytest.fail("the tour ends without the planner")
    shown = []
    monkeypatch.setattr(it, "_on_guidance", lambda step: shown.append(step) or (True, None))
    monkeypatch.setattr("hcs_agent.overlay.screen_size_points", lambda: (1512, 982))
    result = it._dynamic_guide(bound)
    assert [s.where for s in shown] == ["Agents", "Sessions", "Skills"] and all(s.pointer[0] == 100 for s in shown)
    assert result.declared.outcome == "done"
