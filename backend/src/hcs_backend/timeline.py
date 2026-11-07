"""Read an InterventionReport as a story: steps explained -> where the user got stuck -> takeover -> each agent
action -> what the verifier observed. Pure functions over the report dict (no I/O), shared by the dashboard,
the metrics page and the escalation file.

Facts used from the engine (agent/src/hcs_agent/runner.py, backend.py):
- guide traces are `action` steps: "step N shown after X s: <instruction>", "step N (info) shown after X s",
  "no progress after step N (miss k); showing it again", "lost: guiding back to the base screen",
  "autonomy raised to max: taking over", "screen check: ...", grounding lines "locate (i/n): ...";
- the verifier's steps (separate read-only H session) carry attempt == 0;
- the report has no explicit takeover / autonomy field: takeover is read from the traces above.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

STEP_SHOWN = re.compile(r"^step (\d+)( \(info\))? shown after ([\d.]+)s(?::\s*(.*))?$")
NO_PROGRESS = re.compile(r"^no progress after step (\d+)(?: \(miss (\d+)\))?")
TAKEOVER = re.compile(r"taking over|take over|takeover|prends la main", re.I)
SYSTEM = re.compile(r"^(locate \(|screen check:)")


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_timeline(report: dict[str, Any]) -> list[dict[str, Any]]:
    """One entry per meaningful moment: {at, phase, actor, text, seconds?, detail?}.

    phase: explain | stuck | takeover | action | observe | verify | error | system
    actor: guide (the assistant explaining) | agent (acting in the software) | verifier | user
    """
    guidance = {g.get("index"): g for g in report.get("guidance") or []}
    out: list[dict[str, Any]] = []
    for s in report.get("steps") or []:
        summary = str(s.get("summary") or "")
        e: dict[str, Any] = {"at": s.get("timestamp"), "text": summary}
        if s.get("attempt") == 0:
            e.update(phase="verify", actor="verifier")
        elif s.get("kind") == "error":
            e.update(phase="error", actor="agent")
        elif m := STEP_SHOWN.match(summary):
            g = guidance.get(int(m.group(1)), {})
            e.update(phase="explain", actor="guide", step=int(m.group(1)), seconds=float(m.group(3)),
                     text=g.get("instruction") or m.group(4) or f"step {m.group(1)}",
                     detail=g.get("why") or None, info=bool(m.group(2)))
        elif m := NO_PROGRESS.match(summary):
            e.update(phase="stuck", actor="user", step=int(m.group(1)),
                     text=f"No progress after step {m.group(1)}: the step is shown again")
        elif summary.startswith("lost:"):
            e.update(phase="stuck", actor="user", text="Lost: guided back to the base screen")
        elif TAKEOVER.search(summary):
            e.update(phase="takeover", actor="agent", text="The assistant takes over and finishes the task")
        elif SYSTEM.match(summary):
            e.update(phase="system", actor="guide")
        elif s.get("kind") == "action":
            e.update(phase="action", actor="agent")
        else:
            e.update(phase="observe", actor="agent")
        out.append(e)

    v = report.get("verification") or {}
    if v.get("performed"):
        checks = v.get("checks") or {}
        failed = [k for k, ok in checks.items() if not ok]
        out.append({"at": (report.get("timings") or {}).get("finished_at"), "phase": "verify", "actor": "verifier",
                    "text": ("Postcondition observed" if v.get("satisfied") else "Postcondition NOT observed")
                    + (f" — failed checks: {', '.join(failed)}" if failed else ""),
                    "detail": v.get("observed") or None, "final": True})
    return out


def guided_step_seconds(report: dict[str, Any]) -> list[float]:
    """Seconds to show each guided step (from "step N shown after X s"), info steps included."""
    return [float(m.group(3)) for s in report.get("steps") or []
            if (m := STEP_SHOWN.match(str(s.get("summary") or "")))]


def had_takeover(report: dict[str, Any]) -> bool:
    """A guided session where the assistant ended up doing the task itself."""
    return report.get("mode") == "guide" and any(
        TAKEOVER.search(str(s.get("summary") or "")) for s in report.get("steps") or [])


def stuck_count(report: dict[str, Any]) -> int:
    return sum(1 for e in build_timeline(report) if e["phase"] == "stuck")


def duration_s(report: dict[str, Any]) -> float | None:
    t = report.get("timings") or {}
    a, b = _ts(t.get("approved_at") or t.get("started_at")), _ts(t.get("finished_at"))
    return (b - a).total_seconds() if a and b else None


def stop_latency_s(report: dict[str, Any]) -> float | None:
    t = report.get("timings") or {}
    a, b = _ts(t.get("stop_requested_at")), _ts(t.get("stop_effective_at"))
    return (b - a).total_seconds() if a and b else None


def attempts(report: dict[str, Any]) -> int | None:
    """Attempts made by the agent. The engine's own count is in `escalation.attempts`; otherwise, in act mode,
    the distinct `attempt` numbers of the agent's steps. In guide mode `Step.attempt` follows the guide step,
    not the attempt, so it is not counted (None)."""
    esc = report.get("escalation") or {}
    if esc.get("attempts"):
        return int(esc["attempts"])
    if report.get("mode", "act") != "act":
        return None
    nums = {s.get("attempt") for s in report.get("steps") or [] if (s.get("attempt") or 0) > 0}
    return len(nums) or None
