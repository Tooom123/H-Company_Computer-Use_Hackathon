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
    # step index = position in the script (stable when a step is shown again); the optional "open CRM" is skipped
    assert [g.index for g in r.guidance[:-1]] == [2, 3, 4, 5, 6, 7]
    assert all(g.pointer for g in r.guidance[:-1] if g.kind != "info")  # every control step was grounded
    assert any(g.kind == "info" and g.annotations for g in r.guidance)  # To-Do chip shown, not clicked
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


def test_raising_autonomy_mid_guide_hands_over_and_finishes(tmp_path):
    events = []
    it = Intervention(_request("odoo_crm_followup_activity"), MockBackend(step_delay_s=0.01), ProcedureRegistry(),
                      events.append, tmp_path)
    it.start()
    it.approve(ApproveCommand())
    for _ in range(200):
        if it.state is State.awaiting_user:
            break
        time.sleep(0.02)
    assert it.state is State.awaiting_user
    it.set_autonomy(2)  # the user clicks the Magnet's right notch while a step is shown
    it.wait(5)
    assert it.takeover is True
    assert it.report is not None and it.report.status is CaseStatus.resolved
    # the agent took the controls: the session left awaiting_user and ran the act path, then verified
    states = [e.state for e in events if e.type == "state_changed"]
    assert State.running in states[states.index(State.awaiting_user):]
    assert any(e.type == "state_changed" and e.data.get("takeover") for e in events)


def test_lowering_autonomy_mid_guide_keeps_guiding(tmp_path):
    events = []
    it = Intervention(_request("odoo_crm_followup_activity"), MockBackend(step_delay_s=0.01), ProcedureRegistry(),
                      events.append, tmp_path)
    it.start()
    it.approve(ApproveCommand())
    for _ in range(200):
        if it.state is State.awaiting_user:
            break
        time.sleep(0.02)
    it.set_autonomy(0)
    assert it.state is State.awaiting_user  # nothing stops, the step is still waiting for the user
    _auto_next(it, events, [])
    it.wait(5)
    assert it.report.status is CaseStatus.resolved and it.takeover is False


def test_new_voice_request_mid_task_stops_the_current_one(tmp_path, monkeypatch):
    """⌘H during a task: the transcript queue fills, the guide loop stops the intervention right away."""
    import queue
    from types import SimpleNamespace

    from hcs_agent import cli
    from hcs_agent.contract import InterventionRequest

    # This regression observes a transcript queue, not native keyboard/mouse devices.
    monkeypatch.setattr(cli, "_InputWatcher", lambda: SimpleNamespace(stop=lambda: None))
    q: "queue.Queue[str]" = queue.Queue()
    q.put("en fait montre-moi autre chose")
    monkeypatch.setitem(cli._VOICE, "ptt", SimpleNamespace(transcripts=q))
    monkeypatch.setitem(cli._MAGNET, "level", 1)
    req = InterventionRequest(software="odoo", goal="g", procedure_id="odoo_crm_create_opportunity",
                              parameters={"opportunity": "Acme Demo"})
    code = cli._execute(req, MockBackend(step_delay_s=0.01), tmp_path, auto_approve=True, overlay=False, ov=None)
    it = cli._MAGNET["current"]
    assert code == 3 and it.report.status is CaseStatus.abandoned
    assert it.report.timings.stop_requested_at is not None
    assert not q.empty()  # the new request is still queued for the talk loop to run next


def test_generic_unscripted_task_runs_with_the_general_agent(tmp_path):
    from hcs_agent.voice import Intent, generic_request

    intent = Intent(procedure_id=None, task="Share the latest session with my team", software="hcompany", mode="guide")
    req = generic_request(intent, doc_context="Docs: open the session, click Share.")
    assert req.procedure_id == "generic" and req.software == "hcompany"
    events = []
    it = Intervention(req, MockBackend(step_delay_s=0.01, outcome="done"), ProcedureRegistry(), events.append, tmp_path)
    it.start()
    assert it.state is State.awaiting_approval and "Share the latest session" in it.plan.objective
    it.approve(ApproveCommand())
    _auto_next(it, events, [])
    it.wait(5)
    assert it.report is not None and it.report.procedure_id == "generic"
    assert it.report.verification.checks.keys() == {"goal_achieved"}


def test_unscripted_guide_plans_steps_from_the_page_catalogue(tmp_path):
    from hcs_agent.voice import Intent, generic_request

    req = generic_request(Intent(procedure_id=None, task="Start a new session", software="hcompany", mode="guide"))
    events = []
    it = Intervention(req, MockBackend(step_delay_s=0.01, outcome="done"), ProcedureRegistry(), events.append, tmp_path)
    it.start()
    it.approve(ApproveCommand())
    _auto_next(it, events, [])
    it.wait(5)
    assert it.report.status is CaseStatus.resolved
    steps = [g for g in it.guidance if not g.last]
    assert steps and all(g.box_exact and g.box for g in steps)  # boxes come from the page catalogue, not vision
    assert it.report.declared.summary == "[simulated] goal reached"
    assert any("planned step" in e.message for e in events if e.type == "step")


def test_plan_first_software_is_guided_from_the_page_with_script_hints(tmp_path):
    """hcompany: a scripted procedure is still guided from the live page; the script's steps are hints."""
    events = []
    req = InterventionRequest(software="hcompany", goal="create an agent", procedure_id="hcompany_platform_create_agent",
                              parameters={"agent_name": "demo-web-reader"}, mode=Mode.guide)
    it = Intervention(req, MockBackend(step_delay_s=0.01, outcome="done"), ProcedureRegistry(), events.append, tmp_path)
    it.start()
    it.approve(ApproveCommand())
    _auto_next(it, events, [])
    it.wait(5)
    assert it.report.status is CaseStatus.resolved
    assert any("planned step" in e.message for e in events if e.type == "step")  # planner, not the script runner
    assert all(g.box_exact for g in it.guidance if not g.last)
