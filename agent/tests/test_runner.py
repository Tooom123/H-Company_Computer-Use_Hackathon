import threading
import time
from pathlib import Path

import pytest

from hcs_agent.backend import MockBackend
from hcs_agent.contract import ApproveCommand, CaseStatus, Category, InterventionRequest, State, StopCommand
from hcs_agent.procedures import ProcedureRegistry
from hcs_agent.runner import Intervention


def _request(procedure_id: str, **params: str) -> InterventionRequest:
    return InterventionRequest(software="odoo", role="new sales rep", goal="Help me follow up Acme Demo",
                               procedure_id=procedure_id, parameters={"opportunity": "Acme Demo",
                                                                      "due_date": "2026-11-14", **params})


def _run(tmp_path: Path, request: InterventionRequest, outcome: str | None = None, approve: bool = True):
    events = []
    it = Intervention(request, MockBackend(step_delay_s=0.01, outcome=outcome), ProcedureRegistry(),
                      events.append, tmp_path)
    it.start()
    assert it.state is State.awaiting_approval
    it.approve(ApproveCommand(approved=approve))
    it.wait(10)
    return it, events


def test_success_case_is_verified_not_declared(tmp_path):
    it, events = _run(tmp_path, _request("odoo_crm_followup_activity"))
    r = it.report
    assert r.status is CaseStatus.resolved
    assert r.declared.outcome == "done"
    assert r.verification.performed and r.verification.satisfied is True
    assert set(r.verification.checks) == {"opportunity_opened", "activity_present", "due_date_correct", "type_todo"}
    assert r.simulated is True and all(e.simulated for e in events)
    assert (tmp_path / request_dir(it) / "report.json").exists()


def test_declared_success_but_failed_verification_escalates(tmp_path):
    it, _ = _run(tmp_path, _request("odoo_crm_followup_activity"), outcome="fail_verify")
    r = it.report
    assert r.declared.outcome == "done"
    assert r.verification.satisfied is False
    assert r.status is CaseStatus.escalated and r.needs_human
    assert r.escalation is not None and r.escalation.attempts == 2  # max_attempts of the procedure
    assert r.category is Category.unknown
    assert "declared success" in r.suspected_cause


def test_blocked_case_escalates_without_retry(tmp_path):
    it, events = _run(tmp_path, _request("odoo_crm_change_stage_restricted"))
    r = it.report
    assert r.declared.outcome == "blocked"
    assert r.status is CaseStatus.escalated
    assert r.category is Category.permissions
    assert r.escalation.attempts == 1
    assert "Access Error" in r.escalation.blocked_on
    assert any(e.type == "needs_human" for e in events)
    assert r.verification.performed is False  # no verification run after a recognised block


def test_nothing_runs_before_approval(tmp_path):
    events = []
    it = Intervention(_request("odoo_crm_followup_activity"), MockBackend(step_delay_s=0.01),
                      ProcedureRegistry(), events.append, tmp_path)
    it.start()
    time.sleep(0.2)
    assert it.state is State.awaiting_approval
    assert not [e for e in events if e.type == "step"]
    it.approve(ApproveCommand(approved=False))
    it.wait(5)
    assert it.report.status is CaseStatus.abandoned and it.report.approved_scope is None


def test_stop_blocks_new_commands_and_measures_latency(tmp_path):
    events = []
    it = Intervention(_request("odoo_crm_followup_activity"), MockBackend(step_delay_s=0.2),
                      ProcedureRegistry(), events.append, tmp_path)
    it.start()
    it.approve(ApproveCommand())
    time.sleep(0.5)
    it.stop(StopCommand(reason="test"))
    it.wait(5)
    assert it.state is State.stopped
    r = it.report
    assert r.status is CaseStatus.abandoned
    assert r.timings.stop_latency_s is not None and r.timings.stop_latency_s < 1.0
    n_steps = len([e for e in events if e.type == "step"])
    time.sleep(0.5)
    assert len([e for e in events if e.type == "step"]) == n_steps  # nothing new after stop


def test_missing_parameter_fails_cleanly(tmp_path):
    events = []
    req = InterventionRequest(software="odoo", goal="x", procedure_id="odoo_crm_followup_activity")
    it = Intervention(req, MockBackend(), ProcedureRegistry(), events.append, tmp_path)
    it.start()
    assert it.state is State.failed
    assert "opportunity" in it.error and "due_date" in it.error


def test_preflight_failure_is_explained(tmp_path, monkeypatch):
    monkeypatch.setenv("HCS_MOCK_PREFLIGHT_FAIL", "1")
    events = []
    it = Intervention(_request("odoo_crm_followup_activity"), MockBackend(), ProcedureRegistry(), events.append,
                      tmp_path)
    it.start()
    assert it.state is State.preflight_failed
    assert it.report.category is Category.environment
    assert "permission" in it.error.lower()


def request_dir(it: Intervention) -> str:
    return it.request.session_id
