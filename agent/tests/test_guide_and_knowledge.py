import threading
import time

from hcs_agent.backend import MockBackend
from hcs_agent.contract import ApproveCommand, CaseStatus, Category, InterventionRequest, Mode, NextCommand, State
from hcs_agent.procedures import ProcedureRegistry
from hcs_agent.runner import Intervention


def _request(procedure_id: str, mode: Mode = Mode.guide) -> InterventionRequest:
    return InterventionRequest(software="odoo", role="new sales rep", goal="Show me how to follow up Acme Demo",
                               procedure_id=procedure_id, mode=mode,
                               parameters={"opportunity": "Acme Demo", "due_date": "2026-11-14"})


def _auto_next(it: Intervention, events: list, notes: list[str]) -> None:
    """Simulate the user clicking Next each time the agent waits."""
    for _ in range(50):
        it.wait(0.05)
        if it.state.terminal:
            return
        if it.state is State.awaiting_user:
            it.next(NextCommand(done=True, note=notes.pop(0) if notes else None))


def test_guide_mode_waits_for_user_between_steps(tmp_path):
    events = []
    it = Intervention(_request("odoo_crm_followup_activity"), MockBackend(step_delay_s=0.01), ProcedureRegistry(),
                      events.append, tmp_path)
    it.start()
    plan = it.plan
    assert plan.mode is Mode.guide
    assert any("Clicking" in x for x in plan.forbidden_actions)
    assert plan.documentation is None  # no automatic web lookup before the plan
    it.approve(ApproveCommand())
    _auto_next(it, events, ["done", "I see the form"])
    it.wait(5)
    r = it.report
    assert r.mode is Mode.guide
    assert r.status is CaseStatus.resolved
    # scripted guide: 7 steps minus the optional "open CRM" (not visible in the mock) + the closing note
    assert len(r.guidance) == 7 and r.guidance[-1].last
    assert [g.index for g in r.guidance] == list(range(1, 8))
    assert all(g.pointer for g in r.guidance[:-1])  # every real step was grounded
    guidance_events = [e for e in events if e.type == "guidance"]
    assert len(guidance_events) == 7
    assert any(e.type == "state_changed" and e.state is State.awaiting_user for e in events)
    assert r.verification.satisfied is True
    assert not any(k.purpose == "explain" for k in r.knowledge)


def test_guide_mode_blocked_escalates_with_doc_lookup(tmp_path):
    events = []
    it = Intervention(_request("odoo_crm_change_stage_restricted"), MockBackend(step_delay_s=0.01),
                      ProcedureRegistry(), events.append, tmp_path)
    it.start()
    it.approve(ApproveCommand())
    _auto_next(it, events, [])
    it.wait(5)
    r = it.report
    assert r.status is CaseStatus.escalated and r.category is Category.permissions
    assert r.declared.outcome == "blocked"
    assert {k.purpose for k in r.knowledge} == {"blocker"}
    assert all(k.simulated for k in r.knowledge)


def test_stop_while_waiting_for_user(tmp_path):
    events = []
    it = Intervention(_request("odoo_crm_followup_activity"), MockBackend(step_delay_s=0.01), ProcedureRegistry(),
                      events.append, tmp_path)
    it.start()
    it.approve(ApproveCommand())
    for _ in range(100):
        if it.state is State.awaiting_user:
            break
        time.sleep(0.02)
    assert it.state is State.awaiting_user
    it.stop()
    it.wait(5)
    assert it.state is State.stopped
    assert it.report.status is CaseStatus.abandoned
    assert it.report.timings.stop_latency_s < 1


def test_plan_grounding_is_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("HCS_GROUND_PLAN", "1")
    it = Intervention(_request("odoo_crm_followup_activity", Mode.act), MockBackend(step_delay_s=0.01),
                      ProcedureRegistry(), lambda e: None, tmp_path)
    it.start()
    assert it.plan.documentation and it.plan.sources
    it.stop()
    it.wait(5)


def test_act_mode_records_agent_lookups(tmp_path):
    events = []
    it = Intervention(_request("odoo_crm_followup_activity", Mode.act), MockBackend(step_delay_s=0.01),
                      ProcedureRegistry(), events.append, tmp_path)
    it.start()
    it.approve(ApproveCommand())
    it.wait(5)
    assert {k.purpose for k in it.report.knowledge} == {"agent_lookup"}  # only when the agent asked
    assert any(e.type == "knowledge" for e in events)
