"""Backends that actually drive the machine.

`HBackend` uses the H Agents API with a `desktop` environment served from this Python process.
`MockBackend` produces explicitly-flagged simulated events so the app and the support backend can be
developed without a Mac that has H permissions. Mock runs are never a validation of the real integration.
"""

from __future__ import annotations

import base64
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field

from .contract import Category, DeclaredResult, Step
from .procedures import BoundProcedure

StepCallback = Callable[[Step], None]


# --------------------------------------------------------------------------- structured answers


class InterventionAnswer(BaseModel):
    """Structured final answer requested from the H agent for an intervention attempt."""

    outcome: Literal["done", "blocked", "unclear"]
    summary: str
    blocker: str | None = Field(default=None, description="Exact text of the error or limit encountered.")
    blocker_category: Literal[
        "usage", "configuration", "permissions", "data", "suspected_product_defect", "environment", "unknown"
    ] | None = None
    steps_taken: list[str] = Field(default_factory=list)

    def to_declared(self) -> DeclaredResult:
        return DeclaredResult(
            outcome=self.outcome,
            summary=self.summary,
            blocker=self.blocker,
            blocker_category=Category(self.blocker_category) if self.blocker_category else None,
            steps_taken=self.steps_taken,
        )


class VerificationAnswer(BaseModel):
    """Structured answer of the read-only verification session."""

    checks: dict[str, bool] = Field(description="One boolean per check key, as observed on screen.")
    observed: str = Field(description="Plain description of what is visible, including any discrepancy.")


# --------------------------------------------------------------------------- results


@dataclass
class AttemptResult:
    h_session_id: str | None
    status: str  # completed | failed | timed_out | interrupted | simulated
    declared: DeclaredResult
    error: str | None = None
    cost_usd: float | None = None
    agent_view_url: str | None = None


@dataclass
class VerifyResult:
    h_session_id: str | None
    status: str
    checks: dict[str, bool] = field(default_factory=dict)
    observed: str = ""
    error: str | None = None
    cost_usd: float | None = None


class PreflightError(RuntimeError):
    """Raised when the machine cannot be driven (permissions, missing key)."""


# --------------------------------------------------------------------------- protocol


class Backend(Protocol):
    simulated: bool

    def preflight(self) -> None: ...

    def run_attempt(
        self,
        bound: BoundProcedure,
        task: str,
        attempt: int,
        on_step: StepCallback,
        stop_event: threading.Event,
    ) -> AttemptResult: ...

    def verify(
        self,
        bound: BoundProcedure,
        on_step: StepCallback,
        stop_event: threading.Event,
    ) -> VerifyResult: ...

    def screenshot(self, path: Path) -> Path | None: ...


# --------------------------------------------------------------------------- real H backend


class HBackend:
    """Drives this Mac through H's desktop environment."""

    simulated = False

    def __init__(
        self,
        *,
        model: str = "holo4-35b-a3b",
        screenshot_max_width: int = 1280,
        timezone_name: str = "Europe/Paris",
        api_key: str | None = None,
    ) -> None:
        from hai_agents import Client

        self._client = Client(api_key=api_key) if api_key else Client()
        self.model = model
        self.screenshot_max_width = screenshot_max_width
        self.timezone_name = timezone_name
        self._client_lock = threading.Lock()

    # ----------------------------------------------------------------- preflight

    def preflight(self) -> None:
        if sys.platform == "darwin":
            from hai_agents_local.desktop import ensure_macos_input_permissions

            try:
                ensure_macos_input_permissions(prompt=True)
            except PermissionError as exc:
                raise PreflightError(str(exc)) from exc

    # ----------------------------------------------------------------- agent specs

    def _agent_spec(self, name: str, instructions: str, lazy: bool = False) -> dict[str, Any]:
        return {
            "name": name,
            "description": "Customer-success assistant driving the user's own desktop.",
            "model": self.model,
            "instructions": instructions,
            "environments": [
                {
                    "id": "user-mac",
                    "kind": "desktop",
                    "lazy": lazy,
                    "screenshot_max_width": self.screenshot_max_width,
                }
            ],
        }

    # ----------------------------------------------------------------- streaming helper

    def _run(
        self,
        *,
        agent: dict[str, Any],
        message: str,
        answer_schema: type[BaseModel],
        max_steps: int,
        max_time_s: float,
        attempt: int,
        on_step: StepCallback,
        stop_event: threading.Event,
        group_id: str,
    ) -> tuple[Any, str | None]:
        """Start a session, stream its events as Steps, honour stop, return (result, session_id)."""
        if stop_event.is_set():
            return None, None
        handle = self._client.start_session(
            agent=agent,
            messages=message,
            answer_schema=answer_schema,
            max_steps=max_steps,
            max_time_s=max_time_s,
            timezone=self.timezone_name,
            group_id=group_id,
        )
        session_id = handle.id
        index = 0
        done = threading.Event()

        def watch_stop() -> None:
            # Local stop gate: as soon as the user asks, ask H to cancel. Polling keeps the thread
            # releasable when the session ends on its own.
            while not done.is_set():
                if stop_event.wait(0.2):
                    try:
                        handle.cancel()
                    except Exception:  # noqa: BLE001 - best effort, session may already be over
                        pass
                    return

        watcher = threading.Thread(target=watch_stop, daemon=True)
        watcher.start()
        try:
            for event in handle.stream(until="terminal"):
                step = _event_to_step(event, index, attempt)
                if step is not None:
                    on_step(step)
                    index += 1
            result = handle.wait_for_completion()
        finally:
            done.set()
        return result, session_id

    # ----------------------------------------------------------------- public API

    def run_attempt(
        self,
        bound: BoundProcedure,
        task: str,
        attempt: int,
        on_step: StepCallback,
        stop_event: threading.Event,
    ) -> AttemptResult:
        proc = bound.procedure
        agent = self._agent_spec(f"hcs-{proc.id}", bound.agent_instructions)
        try:
            result, sid = self._run(
                agent=agent,
                message=task,
                answer_schema=InterventionAnswer,
                max_steps=proc.max_steps_per_attempt,
                max_time_s=proc.max_time_s_per_attempt,
                attempt=attempt,
                on_step=on_step,
                stop_event=stop_event,
                group_id=bound.request.session_id,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced in the report as agent_failure
            return AttemptResult(None, "failed", DeclaredResult(outcome="not_run"), error=repr(exc))
        if result is None:
            return AttemptResult(sid, "interrupted", DeclaredResult(outcome="not_run"))
        declared = (
            result.answer.to_declared()
            if isinstance(result.answer, InterventionAnswer)
            else DeclaredResult(outcome="unclear", summary=str(result.answer or ""))
        )
        return AttemptResult(
            sid,
            result.status,
            declared,
            error=result.error,
            cost_usd=_total_cost(result.events),
        )

    def verify(
        self,
        bound: BoundProcedure,
        on_step: StepCallback,
        stop_event: threading.Event,
    ) -> VerifyResult:
        checks = bound.checks
        agent = self._agent_spec(f"hcs-verify-{bound.procedure.id}", bound.verification_instructions, lazy=False)
        message = (
            "Verify the following checks by observing the screen. Answer with one boolean per key.\n"
            + "\n".join(f"- {k}: {v}" for k, v in checks.items())
        )
        try:
            result, sid = self._run(
                agent=agent,
                message=message,
                answer_schema=VerificationAnswer,
                max_steps=15,
                max_time_s=180,
                attempt=0,
                on_step=on_step,
                stop_event=stop_event,
                group_id=bound.request.session_id,
            )
        except Exception as exc:  # noqa: BLE001
            return VerifyResult(None, "failed", error=repr(exc))
        if result is None:
            return VerifyResult(sid, "interrupted")
        if not isinstance(result.answer, VerificationAnswer):
            return VerifyResult(sid, result.status, error=result.error or "no structured verification answer")
        # Only keep the keys we asked for; a missing key counts as not verified.
        observed_checks = {k: bool(result.answer.checks.get(k, False)) for k in checks}
        return VerifyResult(
            sid, result.status, observed_checks, result.answer.observed, cost_usd=_total_cost(result.events)
        )

    def screenshot(self, path: Path) -> Path | None:
        try:
            from hai_drivers.desktop.local import LocalDesktopDriver

            driver = LocalDesktopDriver()
            try:
                data = base64.b64decode(driver.screenshot_b64())
            finally:
                driver.close()
        except Exception:  # noqa: BLE001 - evidence is optional
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


def _event_to_step(event: Any, index: int, attempt: int) -> Step | None:
    """Map an H session event to a compact Step for the report. Returns None for noise."""
    etype = getattr(event, "type", None)
    data = getattr(event, "data", None)
    ts = getattr(event, "timestamp", None) or datetime.now(timezone.utc)
    d = _as_dict(data)
    if etype == "AgentEvent":
        kind = d.get("kind")
        if kind == "policy_event":
            reqs = d.get("tool_reqs") or []
            actions = [f"{r.get('tool_name')}({_short(r.get('args'))})" for r in reqs]
            summary = d.get("content") or "; ".join(actions) or "agent decided"
            return Step(index=index, attempt=attempt, timestamp=ts, kind="action", summary=summary[:300],
                        detail={"actions": actions, "reasoning": _short(d.get("reasoning_content"), 500)})
        if kind == "observation_event":
            img = (d.get("image") or {}).get("source")
            return Step(index=index, attempt=attempt, timestamp=ts, kind="observation", summary="screen observed",
                        detail={"screenshot_url": img})
        if kind == "error_event":
            return Step(index=index, attempt=attempt, timestamp=ts, kind="error", summary=str(d.get("error"))[:300])
        if kind == "answer_event":
            return Step(index=index, attempt=attempt, timestamp=ts, kind="answer", summary="agent answered",
                        detail={"outcome": d.get("outcome")})
        if kind == "message_event":
            return Step(index=index, attempt=attempt, timestamp=ts, kind="message",
                        summary=_short(d.get("content"), 300))
        return None
    if etype == "AgentErrorEvent":
        return Step(index=index, attempt=attempt, timestamp=ts, kind="error", summary=str(d.get("error"))[:300])
    return None


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(getattr(obj, "__dict__", {}))


def _short(value: Any, n: int = 80) -> str:
    s = "" if value is None else str(value)
    return s if len(s) <= n else s[: n - 1] + "…"


def _total_cost(events: list[Any]) -> float | None:
    cost = None
    for e in events or []:
        if getattr(e, "type", None) == "MetricsUpdateEvent":
            m = _as_dict(getattr(e, "data", None)).get("metrics") or {}
            m = _as_dict(m)
            if m.get("total_cost") is not None:
                cost = m["total_cost"]
    return cost


# --------------------------------------------------------------------------- mock backend


class MockBackend:
    """Simulates H for UI/backend development. Every step is flagged `simulated`.

    Scenario is picked from the procedure id and the `HCS_MOCK_OUTCOME` env var
    (`done` | `blocked` | `fail_verify`), default: `done` for reversible procedures, `blocked` otherwise.
    """

    simulated = True

    def __init__(self, step_delay_s: float = 0.4, outcome: str | None = None) -> None:
        self.step_delay_s = step_delay_s
        self.outcome = outcome or os.environ.get("HCS_MOCK_OUTCOME")

    def preflight(self) -> None:
        if os.environ.get("HCS_MOCK_PREFLIGHT_FAIL"):
            raise PreflightError("Simulated: Screen Recording permission missing for this process.")

    def _scenario(self, bound: BoundProcedure) -> str:
        return self.outcome or ("done" if bound.procedure.reversible else "blocked")

    def _emit(self, on_step: StepCallback, stop_event: threading.Event, attempt: int, summaries: list[str]) -> bool:
        for i, s in enumerate(summaries):
            if stop_event.is_set():
                return False
            time.sleep(self.step_delay_s)
            on_step(Step(index=i, attempt=attempt, timestamp=datetime.now(timezone.utc),
                         kind="action" if i % 2 else "observation", summary=f"[simulated] {s}"))
        return True

    def run_attempt(self, bound, task, attempt, on_step, stop_event) -> AttemptResult:
        scenario = self._scenario(bound)
        steps = [
            "screen observed: Odoo CRM pipeline",
            f"click on opportunity '{bound.values.get('opportunity', '?')}'",
            "screen observed: opportunity form",
            "click 'Activities'",
        ]
        if scenario == "blocked":
            steps += ["screen observed: 'Access Error: you are not allowed to modify this record'"]
            declared = DeclaredResult(outcome="blocked", summary="An access error dialog appeared.",
                                      blocker="Access Error: You are not allowed to modify 'Lead/Opportunity' records.",
                                      blocker_category=Category.permissions, steps_taken=steps[:4])
        else:
            steps += ["fill activity dialog", "click 'Schedule'", "screen observed: activity listed"]
            declared = DeclaredResult(outcome="done", summary="Activity scheduled.", steps_taken=steps)
        completed = self._emit(on_step, stop_event, attempt, steps)
        return AttemptResult("sim_" + bound.request.session_id, "simulated" if completed else "interrupted",
                             declared if completed else DeclaredResult(outcome="not_run"), cost_usd=0.0)

    def verify(self, bound, on_step, stop_event) -> VerifyResult:
        scenario = self._scenario(bound)
        ok = self._emit(on_step, stop_event, 0, ["reload page", "open opportunity", "read activities"])
        if not ok:
            return VerifyResult(None, "interrupted")
        satisfied = scenario == "done"
        checks = {k: satisfied for k in bound.checks}
        if scenario == "fail_verify":
            checks = {k: (i == 0) for i, k in enumerate(bound.checks)}
        return VerifyResult("sim_verify_" + bound.request.session_id, "simulated", checks,
                            "[simulated] " + ("all checks visible" if satisfied else "expected element not found"),
                            cost_usd=0.0)

    def screenshot(self, path: Path) -> Path | None:
        return None


def make_backend(mock: bool | None = None) -> Backend:
    if mock is None:
        mock = os.environ.get("HCS_MOCK", "").lower() in {"1", "true", "yes"}
    return MockBackend() if mock else HBackend(
        model=os.environ.get("HCS_MODEL", "holo4-35b-a3b"),
        screenshot_max_width=int(os.environ.get("HCS_SCREENSHOT_MAX_WIDTH", "1280")),
    )
