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
    assert "not among the listed controls" in guide.calls[1][4][-1]


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
        "done": False, "instruction": "Click the Build button.", "kind": "click", "target": 1}
    result = guide.it._dynamic_guide(guide.bound)
    assert result is None  # handed over instead of looping to the step limit
    assert len(guide.shown) == 2
    assert any("already gave the step" in h for h in guide.calls[-1][4])


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
