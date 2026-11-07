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

from hai_agents.polling import AnswerValidationError

from .contract import Category, DeclaredResult, GuidanceStep, Step
from .knowledge import DocAnswer, Knowledge, NoKnowledge
from .procedures import BoundProcedure

StepCallback = Callable[[Step], None]
LookupCallback = Callable[[DocAnswer], None]
# Guide mode: called with each step; must block until the user answers and return (done, note), or None on stop.
GuidanceCallback = Callable[[GuidanceStep], "tuple[bool, str | None] | None"]


# --------------------------------------------------------------------------- structured answers


class InterventionAnswer(BaseModel):
    """Structured final answer requested from the H agent for an intervention attempt.

    The field is named `result`, not `outcome`: H reserves `outcome` at session level and strips it
    from the answer payload.
    """

    result: Literal["done", "blocked", "unclear"] | None = Field(
        default=None, description="done if the task was completed, blocked if something prevented it, else unclear.")
    summary: str = ""
    blocker: str | None = Field(default=None, description="Exact text of the error or limit encountered.")
    blocker_category: Literal[
        "usage", "configuration", "permissions", "data", "suspected_product_defect", "environment", "unknown"
    ] | None = None
    steps_taken: list[str] = Field(default_factory=list)

    def to_declared(self, session_outcome: str | None = None) -> DeclaredResult:
        outcome = self.result or _OUTCOME_MAP.get(session_outcome or "", "unclear")
        return DeclaredResult(
            outcome=outcome,
            summary=self.summary,
            blocker=self.blocker,
            blocker_category=Category(self.blocker_category) if self.blocker_category else None,
            steps_taken=self.steps_taken,
        )


# H's self-assessed session outcome -> our declared outcome, used when the answer omits `result`.
_OUTCOME_MAP = {"success": "done", "blocked": "blocked", "infeasible": "blocked", "partial": "unclear"}


def _lenient(model: type[BaseModel], raw: Any) -> BaseModel | None:
    """Parse a possibly incomplete answer: unknown keys ignored, missing ones defaulted when possible."""
    if raw is None:
        return None
    try:
        if isinstance(raw, str):
            return model.model_validate_json(raw)
        return model.model_validate(raw)
    except Exception:  # noqa: BLE001
        return None


class GuideAnswer(BaseModel):
    """One guidance step, answered by the H agent in guide mode."""

    instruction: str = Field(description="What the user should do now, in plain words.")
    where: str = Field(default="", description="Where the control is on screen.")
    why: str = Field(default="", description="What this step achieves for the user.")
    last: bool = Field(default=False, description="True when the goal is visibly achieved or the user is blocked.")
    blocked: bool = Field(default=False, description="True if the user cannot proceed (error, permission).")
    blocker: str | None = Field(default=None, description="Exact message seen on screen when blocked.")


class VerificationAnswer(BaseModel):
    """Structured answer of the read-only verification session."""

    checks: dict[str, bool] = Field(default_factory=dict, description="One boolean per check key, as observed on screen.")
    observed: str = Field(default="", description="Plain description of what is visible, including any discrepancy.")


# --------------------------------------------------------------------------- results


@dataclass
class AttemptResult:
    h_session_id: str | None
    status: str  # completed | failed | timed_out | interrupted | simulated
    declared: DeclaredResult
    error: str | None = None
    cost_usd: float | None = None
    agent_view_url: str | None = None
    guidance: list[GuidanceStep] = field(default_factory=list)


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
    knowledge: Knowledge

    def preflight(self) -> None: ...

    def run_attempt(self, bound: BoundProcedure, task: str, attempt: int, on_step: StepCallback,
                    stop_event: threading.Event, on_lookup: LookupCallback | None = None) -> AttemptResult: ...

    def run_guidance(self, bound: BoundProcedure, task: str, on_step: StepCallback, on_guidance: GuidanceCallback,
                     stop_event: threading.Event, on_lookup: LookupCallback | None = None) -> AttemptResult: ...

    def verify(self, bound: BoundProcedure, on_step: StepCallback, stop_event: threading.Event) -> VerifyResult: ...

    def screenshot(self, path: Path) -> Path | None: ...


def make_lookup_tool(knowledge: Knowledge, software: str, on_lookup: LookupCallback | None):
    """Custom H tool: the agent consults the vendor documentation (Linkup) when unsure."""

    def lookup_docs(question: str) -> str:
        """Search the software's official documentation. Use it when unsure about a menu path, a button name,
        what a feature does, or what an error message means. Ask a precise question."""
        ans = knowledge.ask(question, software=software, depth="fast")
        if ans is None:
            return "Documentation lookup unavailable. Rely on what you see on screen."
        if on_lookup:
            on_lookup(ans)
        return ans.as_text()

    return lookup_docs


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
        knowledge: Knowledge | None = None,
    ) -> None:
        from hai_agents import Client

        self._client = Client(api_key=api_key) if api_key else Client()
        self.model = model
        self.screenshot_max_width = screenshot_max_width
        self.timezone_name = timezone_name
        self.knowledge = knowledge or NoKnowledge()

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
            "name": _agent_name(name),
            "description": "Customer-success assistant driving the user's own desktop.",
            "model": self.model,
            "instructions": instructions,
            "environments": [
                # host=user_device is what makes the SDK serve this Mac from this process; without it H
                # provisions a cloud desktop and the screen seen by the agent is not the user's.
                {"id": "user-mac", "kind": "desktop", "host": "user_device", "lazy": lazy,
                 "screenshot_max_width": self.screenshot_max_width}
            ],
        }

    # ----------------------------------------------------------------- session helpers

    def _watch_stop(self, handle: Any, stop_event: threading.Event, done: threading.Event) -> None:
        # Local stop gate: as soon as the user asks, ask H to cancel. Polling keeps the thread
        # releasable when the session ends on its own.
        while not done.is_set():
            if stop_event.wait(0.2):
                try:
                    handle.cancel()
                except Exception:  # noqa: BLE001 - best effort, session may already be over
                    pass
                return

    def _turn(self, handle: Any, from_index: int, attempt: int, on_step: StepCallback,
              step_offset: int) -> tuple[Any, int, int]:
        """Stream one turn until the session settles (terminal or idle); return (result, next_index, steps).

        Custom tools are the handle's own: stream() and wait_for_completion() share them and run each
        call once, so none is passed explicitly here.
        """
        index = step_offset
        for event in handle.stream(from_index=from_index, until="settled"):
            step = _event_to_step(event, index, attempt)
            if step is not None:
                on_step(step)
                index += 1
        # Session is settled: this returns immediately with the parsed answer and the cursor.
        result = handle.wait_for_completion(from_index=from_index)
        return result, result.next_from_index, index

    # ----------------------------------------------------------------- public API

    def run_attempt(self, bound, task, attempt, on_step, stop_event, on_lookup=None) -> AttemptResult:
        proc = bound.procedure
        if stop_event.is_set():
            return AttemptResult(None, "interrupted", DeclaredResult(outcome="not_run"))
        tools = [make_lookup_tool(self.knowledge, bound.request.software, on_lookup)]
        agent = self._agent_spec(f"hcs-{proc.id}", bound.agent_instructions)
        done = threading.Event()
        sid = None
        try:
            handle = self._client.start_session(
                agent=agent, messages=task, answer_schema=InterventionAnswer, tools=tools,
                max_steps=proc.max_steps_per_attempt, max_time_s=proc.max_time_s_per_attempt,
                timezone=self.timezone_name, group_id=bound.request.session_id,
            )
            sid = handle.id
            threading.Thread(target=self._watch_stop, args=(handle, stop_event, done), daemon=True).start()
            result, _, _ = self._turn(handle, 0, attempt, on_step, 0)
        except AnswerValidationError as exc:
            # The session finished; only the answer shape is off. Keep what the agent said.
            status = self._client.sessions.get_session_status(sid)
            ans = _lenient(InterventionAnswer, exc.raw)
            declared = (ans.to_declared(status.outcome) if ans
                        else DeclaredResult(outcome=_OUTCOME_MAP.get(status.outcome or "", "unclear"),
                                            summary=str(exc.raw)[:500]))
            return AttemptResult(sid, status.status, declared, cost_usd=None)
        except Exception as exc:  # noqa: BLE001 - surfaced in the report as agent_failure
            return AttemptResult(sid, "failed", DeclaredResult(outcome="not_run"), error=_error_text(exc))
        finally:
            done.set()
        if stop_event.is_set() or result.status == "interrupted":
            return AttemptResult(sid, "interrupted", DeclaredResult(outcome="not_run"))
        declared = (result.answer.to_declared(result.outcome) if isinstance(result.answer, InterventionAnswer)
                    else DeclaredResult(outcome=_OUTCOME_MAP.get(result.outcome or "", "unclear"),
                                        summary=str(result.answer or "")))
        return AttemptResult(sid, result.status, declared, error=result.error, cost_usd=_total_cost(result.events))

    def run_guidance(self, bound, task, on_step, on_guidance, stop_event, on_lookup=None) -> AttemptResult:
        """Interactive session: one guidance step per turn, the user performs it, then we continue."""
        proc = bound.procedure
        if stop_event.is_set():
            return AttemptResult(None, "interrupted", DeclaredResult(outcome="not_run"))
        tools = [make_lookup_tool(self.knowledge, bound.request.software, on_lookup)]
        agent = self._agent_spec(f"hcs-guide-{proc.id}", bound.guide_instructions)
        done = threading.Event()
        guidance: list[GuidanceStep] = []
        sid = None
        cost = 0.0
        try:
            handle = self._client.start_session(
                agent=agent, messages=task, answer_schema=GuideAnswer, tools=tools,
                max_steps=proc.max_steps_per_attempt * 2, idle_timeout_s=900,
                timezone=self.timezone_name, group_id=bound.request.session_id,
            )
            sid = handle.id
            threading.Thread(target=self._watch_stop, args=(handle, stop_event, done), daemon=True).start()
            from_index, step_offset = 0, 0
            for n in range(1, 60):
                result, from_index, step_offset = self._turn(handle, from_index, n, on_step, step_offset)
                cost = _total_cost(result.events) or cost
                if stop_event.is_set() or result.status in {"interrupted", "failed", "timed_out"}:
                    break
                ans = result.answer if isinstance(result.answer, GuideAnswer) else None
                if ans is None:
                    declared = DeclaredResult(outcome="unclear", summary=str(result.answer or ""))
                    break
                pointer = _last_pointer(result.events)
                gs = GuidanceStep(index=n, instruction=ans.instruction, where=ans.where, why=ans.why,
                                  pointer=pointer, last=ans.last or ans.blocked)
                guidance.append(gs)
                if gs.last:
                    on_guidance(gs)  # published to the user; the runner does not wait on a last step
                if ans.blocked:
                    declared = DeclaredResult(outcome="blocked", summary=ans.instruction, blocker=ans.blocker,
                                              steps_taken=[g.instruction for g in guidance])
                    break
                if ans.last:
                    declared = DeclaredResult(outcome="done", summary=ans.instruction,
                                              steps_taken=[g.instruction for g in guidance])
                    break
                reply = on_guidance(gs)  # blocks until the user clicks Next / reports a problem / stops
                if reply is None or stop_event.is_set():
                    break
                did, note = reply
                msg = ("I did it." if did else "I could not do it.") + (f" {note}" if note else "")
                handle.send_message(msg + " Look at the screen and give me the next step.")
            else:
                declared = DeclaredResult(outcome="unclear", summary="Too many guidance steps.")
            if stop_event.is_set():
                return AttemptResult(sid, "interrupted", DeclaredResult(outcome="not_run"), guidance=guidance)
            try:
                handle.cancel()  # the idle session is no longer needed
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            return AttemptResult(sid, "failed", DeclaredResult(outcome="not_run"), error=_error_text(exc), guidance=guidance)
        finally:
            done.set()
        if "declared" not in locals():
            declared = DeclaredResult(outcome="not_run")
        return AttemptResult(sid, "completed", declared, cost_usd=cost, guidance=guidance)

    def verify(self, bound, on_step, stop_event) -> VerifyResult:
        checks = bound.checks
        if stop_event.is_set():
            return VerifyResult(None, "interrupted")
        agent = self._agent_spec(f"hcs-verify-{bound.procedure.id}", bound.verification_instructions)
        message = ("Verify the following checks by observing the screen. Answer with one boolean per key.\n"
                   + "\n".join(f"- {k}: {v}" for k, v in checks.items()))
        done = threading.Event()
        sid = None
        try:
            handle = self._client.start_session(
                agent=agent, messages=message, answer_schema=VerificationAnswer, max_steps=15, max_time_s=180,
                timezone=self.timezone_name, group_id=bound.request.session_id,
            )
            sid = handle.id
            threading.Thread(target=self._watch_stop, args=(handle, stop_event, done), daemon=True).start()
            result, _, _ = self._turn(handle, 0, 0, on_step, 0)
            answer, status, events = result.answer, result.status, result.events
        except AnswerValidationError as exc:
            answer, status, events = _lenient(VerificationAnswer, exc.raw), "completed", []
        except Exception as exc:  # noqa: BLE001
            return VerifyResult(sid, "failed", error=_error_text(exc))
        finally:
            done.set()
        if stop_event.is_set() or status == "interrupted":
            return VerifyResult(sid, "interrupted")
        if not isinstance(answer, VerificationAnswer):
            return VerifyResult(sid, status, error="no structured verification answer")
        # Only keep the keys we asked for; a missing key counts as not verified.
        observed = {k: bool(answer.checks.get(k, False)) for k in checks}
        return VerifyResult(sid, status, observed, answer.observed, cost_usd=_total_cost(events))

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


# --------------------------------------------------------------------------- event mapping


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


def _last_pointer(events: list[Any]) -> tuple[int, int] | None:
    """Coordinates of the last mouse move the agent made in this turn, if any."""
    pointer = None
    for e in events or []:
        d = _as_dict(getattr(e, "data", None))
        if getattr(e, "type", None) != "AgentEvent" or d.get("kind") != "policy_event":
            continue
        for r in d.get("tool_reqs") or []:
            args = _as_dict(r.get("args"))
            if "x" in args and "y" in args:
                try:
                    pointer = (int(args["x"]), int(args["y"]))
                except (TypeError, ValueError):
                    pass
    return pointer


def _agent_name(raw: str) -> str:
    """H agent names: lowercase ASCII letters, digits and hyphens, alphanumeric at both ends, <= 63 chars."""
    import re

    name = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")
    return (name or "hcs-agent")[:63].rstrip("-")


def _error_text(exc: BaseException) -> str:
    body = getattr(exc, "body", None)
    return f"{type(exc).__name__}: {body if body else exc}"[:600]


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
            m = _as_dict(_as_dict(getattr(e, "data", None)).get("metrics"))
            if m.get("total_cost") is not None:
                cost = m["total_cost"]
    return cost


# --------------------------------------------------------------------------- mock backend


class MockBackend:
    """Simulates H for UI/backend development. Every step is flagged `simulated`.

    Scenario comes from the procedure and the `HCS_MOCK_OUTCOME` env var
    (`done` | `blocked` | `fail_verify`), default: `done` for reversible procedures, `blocked` otherwise.
    """

    simulated = True

    def __init__(self, step_delay_s: float = 0.4, outcome: str | None = None, knowledge: Knowledge | None = None):
        self.step_delay_s = step_delay_s
        self.outcome = outcome or os.environ.get("HCS_MOCK_OUTCOME")
        from .knowledge import MockKnowledge

        self.knowledge = knowledge or MockKnowledge()

    def preflight(self) -> None:
        if os.environ.get("HCS_MOCK_PREFLIGHT_FAIL"):
            raise PreflightError("Simulated: Screen Recording permission missing for this process.")

    def _scenario(self, bound: BoundProcedure) -> str:
        return self.outcome or ("done" if bound.procedure.reversible else "blocked")

    def _emit(self, on_step, stop_event, attempt, summaries) -> bool:
        for i, s in enumerate(summaries):
            if stop_event.is_set():
                return False
            time.sleep(self.step_delay_s)
            on_step(Step(index=i, attempt=attempt, timestamp=datetime.now(timezone.utc),
                         kind="action" if i % 2 else "observation", summary=f"[simulated] {s}"))
        return True

    def run_attempt(self, bound, task, attempt, on_step, stop_event, on_lookup=None) -> AttemptResult:
        scenario = self._scenario(bound)
        opp = bound.values.get("opportunity", "?")
        steps = ["screen observed: Odoo CRM pipeline", f"click on opportunity '{opp}'",
                 "screen observed: opportunity form", "click 'Activities'"]
        if on_lookup:
            on_lookup(self.knowledge.ask("How to schedule an activity in Odoo CRM?", bound.request.software))
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

    def run_guidance(self, bound, task, on_step, on_guidance, stop_event, on_lookup=None) -> AttemptResult:
        scenario = self._scenario(bound)
        opp = bound.values.get("opportunity", "?")
        script = [
            ("Open the CRM app from the main menu.", "Top-left app switcher, 'CRM'", "This is where opportunities live."),
            (f"Click the card named '{opp}' in the pipeline.", "Pipeline column, card with that title", "Opens its form."),
            ("Click 'Activities' in the chatter and choose 'To Do'.", "Right side, clock icon", "Creates the follow-up."),
        ]
        guidance: list[GuidanceStep] = []
        for i, (instr, where, why) in enumerate(script, start=1):
            if not self._emit(on_step, stop_event, i, ["screen observed", "mouse moved to the control"]):
                return AttemptResult("sim_" + bound.request.session_id, "interrupted", DeclaredResult(), guidance=guidance)
            blocked = scenario == "blocked" and i == len(script)
            gs = GuidanceStep(index=i, instruction=instr if not blocked else
                              "An 'Access Error' dialog appeared: you are not allowed to do this.", where=where,
                              why=why, pointer=(640 + i * 10, 300 + i * 20), last=i == len(script))
            guidance.append(gs)
            reply = on_guidance(gs)
            if gs.last:
                break
            if reply is None or stop_event.is_set():
                return AttemptResult("sim_" + bound.request.session_id, "interrupted", DeclaredResult(), guidance=guidance)
        if scenario == "blocked":
            declared = DeclaredResult(outcome="blocked", summary=guidance[-1].instruction,
                                      blocker="Access Error: You are not allowed to modify 'Lead/Opportunity' records.",
                                      blocker_category=Category.permissions,
                                      steps_taken=[g.instruction for g in guidance])
        else:
            declared = DeclaredResult(outcome="done", summary="User completed the guided steps.",
                                      steps_taken=[g.instruction for g in guidance])
        return AttemptResult("sim_" + bound.request.session_id, "simulated", declared, cost_usd=0.0, guidance=guidance)

    def verify(self, bound, on_step, stop_event) -> VerifyResult:
        scenario = self._scenario(bound)
        if not self._emit(on_step, stop_event, 0, ["reload page", "open opportunity", "read activities"]):
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
    from .knowledge import make_knowledge

    if mock is None:
        mock = os.environ.get("HCS_MOCK", "").lower() in {"1", "true", "yes"}
    if mock:
        return MockBackend()
    return HBackend(
        model=os.environ.get("HCS_MODEL", "holo4-35b-a3b"),
        screenshot_max_width=int(os.environ.get("HCS_SCREENSHOT_MAX_WIDTH", "1280")),
        knowledge=make_knowledge(),
    )
