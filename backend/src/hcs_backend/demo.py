"""Demo cases for the support dashboard (PRD: "au moins trois sessions de test illustrent le regroupement").

Every case here is flagged demo_data=True and simulated=True: it was written by hand to build and show the
dashboard, it is not the output of a real H run. Scenario: Odoo CRM, a new sales rep (see PRD).
"""

from __future__ import annotations

import copy
from typing import Any

ODOO = {"software": "Odoo CRM", "software_version": "19.0", "os": "macOS 15.5"}

_PLAN_ACTIVITY = {
    "objective": "Schedule a To Do activity on the opportunity 'Acme Démo'",
    "planned_changes": ["Create one To Do activity on 'Acme Démo' due on the chosen date, assigned to the user"],
    "allowed_actions": ["open CRM pipeline", "open opportunity", "create activity"],
    "forbidden_actions": ["send emails", "delete records", "change other fields"],
    "reversible": True,
    "max_attempts": 2,
    "explanation": "Activities are reminders attached to a record; nothing is sent to the customer.",
}

_PLAN_ASSIGN = {
    "objective": "Assign the opportunity 'Globex Démo' to a colleague",
    "planned_changes": ["Change the Salesperson field of 'Globex Démo'"],
    "allowed_actions": ["open CRM pipeline", "open opportunity", "edit salesperson"],
    "forbidden_actions": ["send emails", "delete records", "change access rights"],
    "reversible": True,
    "max_attempts": 2,
    "explanation": "The salesperson owns follow-ups on the opportunity.",
}


def _step(i: int, attempt: int, kind: str, summary: str, minute: int) -> dict[str, Any]:
    return {
        "index": i,
        "attempt": attempt,
        "timestamp": f"2026-11-07T16:{minute:02d}:00Z",
        "kind": kind,
        "summary": summary,
        "detail": {},
    }


def _base(case_id: str, **kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "case_id": case_id,
        "session_id": f"sess-{case_id}",
        **ODOO,
        "role": "new sales rep",
        "session_type": "support",
        "goal": "",
        "symptom": None,
        "procedure_id": None,
        "approved_scope": None,
        "scope_note": None,
        "steps": [],
        "declared": {"outcome": "not_run", "summary": "", "blocker": None, "blocker_category": None, "steps_taken": []},
        "verification": {"performed": False, "satisfied": None, "postcondition": "", "observed": "", "checks": {}, "evidence_refs": [], "user_confirmed": None},
        "status": "abandoned",
        "category": "unknown",
        "suspected_cause": None,
        "needs_human": False,
        "escalation": None,
        "evidence": [],
        "feedback": None,
        "h_session_ids": [],
        "timings": {
            "started_at": "2026-11-07T16:00:00Z",
            "approved_at": "2026-11-07T16:01:00Z",
            "finished_at": "2026-11-07T16:04:00Z",
            "stop_requested_at": None,
            "stop_effective_at": None,
        },
        "cost_usd": None,
        "simulated": True,
        "demo_data": True,
    }
    r.update(kw)
    return r


def resolved_activity() -> dict[str, Any]:
    return _base(
        "demo-001",
        session_type="onboarding",
        goal="Organise the follow-up of the opportunity 'Acme Démo' on 14 November",
        procedure_id="odoo.crm.schedule_activity",
        approved_scope=_PLAN_ACTIVITY,
        steps=[
            _step(0, 1, "observation", "CRM pipeline visible, 'Acme Démo' in stage Qualified", 1),
            _step(1, 1, "action", "Opened 'Acme Démo'", 2),
            _step(2, 1, "action", "Created To Do activity 'Call back Acme' due 2026-11-14", 3),
            _step(3, 1, "observation", "Reopened the record: activity listed under Planned activities", 4),
        ],
        declared={"outcome": "done", "summary": "Activity created on Acme Démo", "blocker": None, "blocker_category": None, "steps_taken": ["open opportunity", "schedule activity"]},
        verification={
            "performed": True,
            "satisfied": True,
            "postcondition": "A To Do activity due 2026-11-14 assigned to the user exists on 'Acme Démo'",
            "observed": "Planned activities shows 'Call back Acme', To Do, due 14/11/2026, assigned to Demo Sales",
            "checks": {"activity_exists": True, "due_date": True, "assignee": True},
            "evidence_refs": ["ev-001-after"],
            "user_confirmed": True,
        },
        status="resolved",
        category="usage",
        evidence=[{"ref": "ev-001-after", "kind": "screenshot", "description": "Record reopened after the change", "path": None, "url": None, "shareable_with_support": True}],
        feedback={"useful": True, "comment": "Clear, I did not know activities existed.", "allow_screenshots_to_support": True},
    )


def blocked_assign(case_id: str, opportunity: str, user_wording: str, comment: str | None) -> dict[str, Any]:
    plan = copy.deepcopy(_PLAN_ASSIGN)
    plan["objective"] = f"Assign the opportunity '{opportunity}' to a colleague"
    blocker = f"Odoo access error: not allowed to modify Opportunity (crm.lead) records when changing the salesperson of '{opportunity}'"
    return _base(
        case_id,
        goal=f"Give the opportunity '{opportunity}' to my colleague",
        symptom=user_wording,
        procedure_id="odoo.crm.assign_salesperson",
        approved_scope=plan,
        steps=[
            _step(0, 1, "observation", f"Opportunity '{opportunity}' open, Salesperson field editable-looking", 1),
            _step(1, 1, "action", "Changed Salesperson and clicked Save", 2),
            _step(2, 1, "error", "Access error dialog: not allowed to modify crm.lead records", 2),
            _step(3, 2, "observation", "Discarded change; access error confirmed, not retried (permission limit)", 3),
        ],
        declared={"outcome": "blocked", "summary": "Saving the salesperson is refused by Odoo", "blocker": blocker, "blocker_category": "permissions", "steps_taken": ["open opportunity", "edit salesperson", "save"]},
        verification={
            "performed": True,
            "satisfied": False,
            "postcondition": f"Salesperson of '{opportunity}' is the chosen colleague",
            "observed": "Salesperson unchanged after reload",
            "checks": {"salesperson_changed": False},
            "evidence_refs": [f"ev-{case_id}-error"],
            "user_confirmed": None,
        },
        status="escalated",
        category="permissions",
        suspected_cause="User group 'Sales / User: Own Documents Only' cannot reassign opportunities",
        needs_human=True,
        escalation={
            "blocked_on": blocker,
            "attempts": 1,
            "decision_expected": "Grant the user the right to reassign opportunities, or reassign it for them",
            "suggested_next_step": "Check the user's Sales access level in Settings > Users",
        },
        evidence=[{"ref": f"ev-{case_id}-error", "kind": "screenshot", "description": "Odoo access error dialog", "path": None, "url": None, "shareable_with_support": True}],
        feedback={"useful": True, "comment": comment, "allow_screenshots_to_support": case_id.endswith("2")},
    )


def config_missing_type() -> dict[str, Any]:
    blocker = "Activity type 'Call' is not available in the activity type list"
    return _base(
        "demo-004",
        session_type="configuration",
        goal="Plan a phone call reminder on 'Initech Démo'",
        procedure_id="odoo.crm.schedule_activity",
        approved_scope=_PLAN_ACTIVITY | {"objective": "Schedule a Call activity on 'Initech Démo'"},
        steps=[
            _step(0, 1, "action", "Opened 'Initech Démo' and the activity dialog", 1),
            _step(1, 1, "observation", "Activity types offered: To Do, Email, Upload Document; no 'Call'", 2),
        ],
        declared={"outcome": "blocked", "summary": "No Call activity type configured", "blocker": blocker, "blocker_category": "configuration", "steps_taken": ["open activity dialog"]},
        verification={"performed": True, "satisfied": False, "postcondition": "A Call activity exists on 'Initech Démo'", "observed": "No activity created", "checks": {"activity_exists": False}, "evidence_refs": [], "user_confirmed": None},
        status="workaround",
        category="configuration",
        suspected_cause="'Call' activity type archived or never created in this database",
        needs_human=True,
        escalation={
            "blocked_on": blocker,
            "attempts": 1,
            "decision_expected": "Restore or create the 'Call' activity type; meanwhile a To Do was proposed",
            "suggested_next_step": "CRM > Configuration > Activity Types",
        },
        feedback={"useful": None, "comment": None, "allow_screenshots_to_support": False},
    )


def demo_cases() -> list[tuple[dict[str, Any], str]]:
    """(report, user_ref) pairs: one resolved, two similar permission blocks, one configuration gap."""
    return [
        (resolved_activity(), "demo-user-alice"),
        (blocked_assign("demo-002", "Globex Démo", "It says access error when I save", "I just wanted to hand it over."), "demo-user-bob"),
        (blocked_assign("demo-003", "Umbrella Démo", "Cannot change the salesperson, error popup", None), "demo-user-chloe"),
        (config_missing_type(), "demo-user-alice"),
    ]
