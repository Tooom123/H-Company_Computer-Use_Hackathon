"""Build the support escalation file from a stored case (PRD: "Gestion d'un blocage", "Escalade").

The file lets a human pick up without redoing the investigation: goal, observed state, what was tried,
where it is blocked and which decision is expected. It keeps apart what the user declared, what the agent
declared and what was actually observed, and it only lists screenshots the user agreed to share.
"""

from __future__ import annotations

from typing import Any

from .store import StoredCase
from .timeline import build_timeline


def shareable_evidence(report: dict[str, Any]) -> list[dict[str, Any]]:
    allow_screens = bool((report.get("feedback") or {}).get("allow_screenshots_to_support"))
    out = []
    for ev in report.get("evidence") or []:
        if ev.get("kind") == "screenshot" and not (allow_screens and ev.get("shareable_with_support")):
            continue
        out.append(ev)
    return out


def withheld_evidence_count(report: dict[str, Any]) -> int:
    return len(report.get("evidence") or []) - len(shareable_evidence(report))


def needs_escalation(report: dict[str, Any]) -> bool:
    return report.get("status") == "escalated" or bool(report.get("needs_human")) or bool(report.get("escalation"))


def build_escalation(case: StoredCase) -> dict[str, Any]:
    r = case.report
    declared = r.get("declared") or {}
    verification = r.get("verification") or {}
    esc = r.get("escalation") or {}
    scope = r.get("approved_scope") or {}
    steps = r.get("steps") or []
    return {
        "case_id": case.case_id,
        "session_id": case.session_id,
        "received_at": case.received_at,
        "simulated": case.simulated,
        "demo_data": case.demo_data,
        "status": r.get("status"),
        "category": r.get("category"),
        "needs_human": bool(r.get("needs_human")),
        "context": {
            "software": r.get("software"),
            "software_version": r.get("software_version"),
            "os": r.get("os"),
            "session_type": r.get("session_type"),
            "procedure_id": r.get("procedure_id"),
        },
        "user_declared": {
            "role": r.get("role"),
            "goal": r.get("goal"),
            "symptom": r.get("symptom"),
            "feedback": r.get("feedback"),
        },
        "approved_scope": {
            "objective": scope.get("objective"),
            "planned_changes": scope.get("planned_changes", []),
            "forbidden_actions": scope.get("forbidden_actions", []),
            "max_attempts": scope.get("max_attempts"),
            "scope_note": r.get("scope_note"),
        }
        if scope
        else None,
        "agent_declared": {
            "outcome": declared.get("outcome"),
            "summary": declared.get("summary"),
            "blocker": declared.get("blocker"),
            "steps_taken": declared.get("steps_taken", []),
        },
        "observed": {
            "verification_performed": verification.get("performed", False),
            "postcondition": verification.get("postcondition"),
            "postcondition_satisfied": verification.get("satisfied"),
            "observed_state": verification.get("observed"),
            "checks": verification.get("checks", {}),
            "user_confirmed": verification.get("user_confirmed"),
        },
        "attempted_steps": [
            {"attempt": s.get("attempt"), "kind": s.get("kind"), "summary": s.get("summary"), "at": s.get("timestamp")}
            for s in steps
            if s.get("kind") in ("action", "error", "observation")
        ],
        # readable course of the session (explained / stuck / takeover / agent / verifier), grounding noise left out
        "session_course": [
            {"at": ev.get("at"), "phase": ev["phase"], "actor": ev["actor"], "text": ev["text"]}
            for ev in build_timeline(r) if ev["phase"] != "system"
        ],
        # what the vendor documentation says about the exact blocker (Linkup lookups with purpose=blocker)
        "documentation": [
            {"query": k.get("query"), "answer": k.get("answer"), "simulated": bool(k.get("simulated")),
             "sources": [{"name": x.get("name"), "url": x.get("url")} for x in k.get("sources") or []]}
            for k in r.get("knowledge") or [] if k.get("purpose") == "blocker"
        ],
        "mode": r.get("mode"),
        "blocked_on": esc.get("blocked_on") or declared.get("blocker"),
        "attempts": esc.get("attempts"),
        "suspected_cause": r.get("suspected_cause"),
        "decision_expected": esc.get("decision_expected"),
        "suggested_next_step": esc.get("suggested_next_step"),
        "evidence": shareable_evidence(r),
        "evidence_withheld": withheld_evidence_count(r),
        "h_session_ids": r.get("h_session_ids", []),
        "timings": r.get("timings", {}),
    }


def _line(label: str, value: Any) -> str:
    return f"- **{label}:** {value if value not in (None, '', []) else '—'}"


def escalation_markdown(case: StoredCase) -> str:
    e = build_escalation(case)
    ctx, user, agent, obs = e["context"], e["user_declared"], e["agent_declared"], e["observed"]
    out: list[str] = []
    title = f"# Case {e['case_id']} — {ctx['software']}"
    out.append(title)
    if e["simulated"] or e["demo_data"]:
        flags = [f for f, on in (("SIMULATED", e["simulated"]), ("DEMO DATA", e["demo_data"])) if on]
        out.append(f"\n> {' · '.join(flags)} — not a real customer case.")
    out += [
        "",
        _line("Status", e["status"]),
        _line("Category", e["category"]),
        _line("Needs a human", "yes" if e["needs_human"] else "no"),
        "",
        "## Decision expected from support",
        "",
        e["decision_expected"] or "— (no escalation requested by the agent)",
        "",
        _line("Blocked on", e["blocked_on"]),
        _line("Attempts", e["attempts"]),
        _line("Suspected cause (hypothesis)", e["suspected_cause"]),
        _line("Suggested next step", e["suggested_next_step"]),
        "",
        "## What the documentation says about the blocker",
        "",
    ]
    for d in e["documentation"]:
        out += [f"- **Q:** {d['query']}" + (" _(simulated)_" if d["simulated"] else ""), f"  **A:** {d['answer']}"]
        out += [f"  - source: [{x['name'] or x['url']}]({x['url']})" for x in d["sources"]]
    if not e["documentation"]:
        out.append("— (no documentation lookup on this blocker)")
    out += [
        "",
        "## Context",
        "",
        _line("Software", f"{ctx['software']} {ctx['software_version'] or ''}".strip()),
        _line("OS", ctx["os"]),
        _line("Session type", ctx["session_type"]),
        _line("Mode", e["mode"]),
        _line("Procedure", ctx["procedure_id"]),
        "",
        "## Declared by the user",
        "",
        _line("Role", user["role"]),
        _line("Goal", user["goal"]),
        _line("Symptom", user["symptom"]),
    ]
    fb = user["feedback"] or {}
    if fb:
        out.append(_line("Feedback", f"useful={fb.get('useful')} — {fb.get('comment') or ''}"))
    if e["approved_scope"]:
        sc = e["approved_scope"]
        out += ["", "## Approved scope", "", _line("Objective", sc["objective"])]
        out += [f"  - change: {c}" for c in sc["planned_changes"]]
        out += [f"  - forbidden: {c}" for c in sc["forbidden_actions"]]
    out += [
        "",
        "## Declared by the agent",
        "",
        _line("Outcome", agent["outcome"]),
        _line("Summary", agent["summary"]),
        _line("Blocker", agent["blocker"]),
        "",
        "## Observed (verification)",
        "",
        _line("Verification performed", obs["verification_performed"]),
        _line("Postcondition", obs["postcondition"]),
        _line("Satisfied", obs["postcondition_satisfied"]),
        _line("Observed state", obs["observed_state"]),
    ]
    out += [f"  - check `{k}`: {'ok' if v else 'FAILED'}" for k, v in obs["checks"].items()]
    out += ["", "## What happened", ""]
    out += [f"{i}. **{ev['phase']}** ({ev['actor']}) {ev['text']}" for i, ev in enumerate(e["session_course"], 1)]
    if not e["session_course"]:
        out.append("—")
    out += ["", "## Evidence", ""]
    out += [f"- `{ev['ref']}` ({ev['kind']}): {ev['description']}" for ev in e["evidence"]]
    if e["evidence_withheld"]:
        out.append(f"- {e['evidence_withheld']} screenshot(s) withheld: the user did not allow sharing them.")
    if not e["evidence"] and not e["evidence_withheld"]:
        out.append("—")
    return "\n".join(out) + "\n"
