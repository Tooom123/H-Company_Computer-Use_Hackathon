"""Reliability metrics per scenario (docs/TODO-tom.md item 4; jury: reliability 25 %).

Honest numbers only: real sessions (simulated reports are counted apart and never mixed in), N always shown,
a metric with no data is None ("—"), never 0. "Success" = postcondition observed by the separate verifier,
not the agent's claim.
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any

from .store import StoredCase
from .timeline import attempts, duration_s, guided_step_seconds, had_takeover, stop_latency_s


def _med(xs: list[float]) -> float | None:
    return median(xs) if xs else None


def _rate(hits: int, n: int) -> float | None:
    return hits / n if n else None


def scenario_metrics(reports: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(reports)
    verified = sum(1 for r in reports if (r.get("verification") or {}).get("satisfied") is True)
    guided = [r for r in reports if r.get("mode") == "guide"]
    step_s = [x for r in guided for x in guided_step_seconds(r)]
    stops = [x for r in reports if (x := stop_latency_s(r)) is not None]
    costs = [float(r["cost_usd"]) for r in reports if r.get("cost_usd") is not None]
    durations = [x for r in reports if (x := duration_s(r)) is not None]
    tries = [a for r in reports if (a := attempts(r)) is not None]
    return {
        "n": n,
        "verified": verified,
        "success_rate": _rate(verified, n),
        "escalated": sum(1 for r in reports if r.get("status") == "escalated"),
        "abandoned": sum(1 for r in reports if r.get("status") == "abandoned"),
        "n_guided": len(guided),
        "median_s_per_guided_step": _med(step_s),
        "n_guided_steps": len(step_s),
        "takeover_rate": _rate(sum(1 for r in guided if had_takeover(r)), len(guided)),
        "median_stop_latency_s": _med(stops),
        "n_stops": len(stops),
        "mean_cost_usd": mean(costs) if costs else None,
        "median_duration_s": _med(durations),
        "mean_attempts": mean(tries) if tries else None,
    }


def compute(cases: list[StoredCase]) -> dict[str, Any]:
    real = [c for c in cases if not c.simulated]
    by: dict[str, list[dict[str, Any]]] = {}
    for c in real:
        by.setdefault(c.report.get("procedure_id") or "(no procedure)", []).append(c.report)
    return {
        "scenarios": {k: scenario_metrics(v) for k, v in sorted(by.items())},
        "overall": scenario_metrics([c.report for c in real]),
        "excluded_simulated": len(cases) - len(real),
    }
