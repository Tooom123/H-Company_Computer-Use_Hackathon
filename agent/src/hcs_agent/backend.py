"""Backends that actually drive the machine.

`HBackend` uses the H Agents API with a `desktop` environment served from this Python process.
`MockBackend` produces explicitly-flagged simulated events so the app and the support backend can be
developed without a Mac that has H permissions. Mock runs are never a validation of the real integration.
"""

from __future__ import annotations

import base64
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from hai_agents.polling import AnswerValidationError
from hai_agents_local.desktop import PyautoguiDesktopBridge

from .contract import Category, DeclaredResult, GuidanceStep, Step
from .grounding import Located
from .knowledge import DocAnswer, Knowledge, NoKnowledge
from .procedures import BoundProcedure, RESPONSE_LANGUAGE_INSTRUCTIONS

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


class GuideTarget(BaseModel):
    """A point in the explicit full-screenshot normalized frame, never guessed pixels."""

    target_x: float | None = Field(default=None, ge=0, le=1000,
        description="Horizontal position normalized to 0..1000 across the FULL screenshot: 0 left, 1000 right. Null if uncertain.")
    target_y: float | None = Field(default=None, ge=0, le=1000,
        description="Vertical position normalized to 0..1000 across the FULL screenshot: 0 top, 1000 bottom. Null if uncertain.")

    @field_validator("target_x", "target_y", mode="before")
    @classmethod
    def valid_coordinate_or_none(cls, value):
        # Keep useful guidance text even if the model supplies an invalid point.
        if type(value) not in (int, float) or not 0 <= value <= 1000 or not math.isfinite(value):
            return None
        return value


class GuideSubStep(GuideTarget):
    instruction: str = Field(default="", description="One short imperative line, max 12 words.")
    where: str | None = ""
    why: str | None = ""
    kind: Literal["click", "type", "key", "info", "wait"] = Field(default="click",
        description="Expected human interaction: click, type, key, info (read only), or wait (observe a pending result).")
    done_when: str | None = Field(default=None,
        description="Concrete visible state to verify after this interaction. A click alone is not completion.")


class GuideAnswer(GuideTarget):
    """Guidance answered by the H agent in guide mode: the next step, plus following steps visible on the same screen."""

    steps: list[GuideSubStep] | None = Field(
        default=None,
        description="Up to 3 consecutive steps whose controls are ALL visible on the current screen, in order. "
                    "The first one must also be repeated in the top-level fields. Only the first is shown; the "
                    "others prepare audio and must be revalidated on a fresh screen before use.")
    instruction: str = Field(default="", description="What the user should do now. One short line, max 12 words.")
    where: str | None = Field(default="", description="Where the control is on screen, in words.")
    why: str | None = Field(default="", description="One or two sentences: what this step achieves for the user.")
    kind: Literal["click", "type", "key", "info", "wait"] = Field(default="click",
        description="Expected human interaction: click, type, key, info (read only), or wait (observe a pending result).")
    done_when: str | None = Field(default=None,
        description="Concrete visible state to verify after this interaction. A click alone is not completion.")
    coordinate_system: Literal["normalized_1000"] | None = Field(default=None,
        description="Set normalized_1000 explicitly whenever returning a target, including targets in steps. Applies to both axes and every step. Never pixels or viewport coordinates.")
    last: bool | None = Field(default=False, description="True when the goal is visibly achieved or the user is blocked.")
    blocked: bool | None = Field(default=False, description="True if the user cannot proceed (error, permission).")
    blocker: str | None = Field(default=None, description="Exact message seen on screen when blocked.")

    @field_validator("coordinate_system", mode="before")
    @classmethod
    def explicit_coordinate_system_or_none(cls, value):
        return value if value == "normalized_1000" else None

    def model_post_init(self, __context) -> None:
        self.where, self.why = self.where or "", self.why or ""
        self.last, self.blocked = bool(self.last), bool(self.blocked)
        self.steps = [x for x in (self.steps or []) if x.instruction]


_GUIDANCE_PROGRESSION = """\
Progression protocol: only the first proposed step is shown. Following steps are tentative audio
preparation, never permission to advance without observing the screen again. Give the current step's
kind and, where possible, done_when: a visible postcondition, not just an input event.
An 'Observed interaction:' message is an automatic input or screen-change signal, NOT human feedback
or proof of success. A 'User reported' message is a declaration, also not verified success. After either,
take a fresh screenshot, check the previous expected result, then adapt the next instruction and target
to the actual current screen. Never reuse the previous batch or declare completion just because an
input occurred. Stay within the reference procedure and observation-only tool permissions.
"""


def _guidance_reply_message(done: bool, note: str | None, expected: str | None) -> str:
    """Preserve automatic signals versus human declarations; neither proves a postcondition."""
    note = (note or "").strip()
    if note.startswith("Observed interaction:"):
        signal = note
    else:
        signal = ("User reported completing the interaction." if done
                  else "User reported difficulty completing the interaction.")
        if note:
            signal += f" User note: {note}"
    expected_result = f" Expected visible result to verify: {expected}." if expected else ""
    return (signal + " This is not a verified outcome." + expected_result
            + " Take a fresh screenshot and verify the result before choosing the next instruction."
              " Adapt to the current screen; discard any stale remaining steps from the previous answer.")


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

    def locate(self, description: str, context: str = "") -> "Located | None": ...

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


class ReadOnlyDesktopBridge(PyautoguiDesktopBridge):
    """Enforce GUIDE observation at the local command boundary, before driver access.

    Names are SDK wire methods, not model tool names. Every other method (including
    future methods) is denied. Local overlay drawing remains outside this bridge.
    This does not redact sensitive information visible on the user's screen.
    """

    commands = frozenset({
        "platform", "screenshot_b64", "get_screen_size", "get_mouse_position",
        "get_observation_snapshot",
    })

    def _dispatch(self, name, args):
        if name not in self.commands or args:
            return None, "GUIDE observation only: desktop input, files and shell are disabled."
        # Do not call the base dispatcher: it logs raw driver exceptions, which
        # may contain private paths or credentials. These methods take no args.
        from hai_agents_local.transport import serialize_result

        try:
            method = getattr(self._driver, name)
            return serialize_result(method() if callable(method) else method), None
        except Exception:
            return None, "GUIDE observation unavailable; no desktop action was performed."


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
        # Freeze the permission for this backend/channel; a later environment
        # edit must not upgrade an already running observation-only session.
        self.observe_only = os.environ.get("HCS_GUIDE_OBSERVE_ONLY", "").lower() in {"1", "true", "yes"}
        self._desktop_session_id: str | None = None
        if not self.observe_only and os.environ.get("HCS_AUTO_CLEANUP", "1") not in {"0", "false", "no"}:
            self._close_orphans()

    def _close_orphans(self) -> None:
        """Close command channels left pending by earlier dead processes: each one holds a concurrency slot."""
        if getattr(self, "observe_only", False):
            return  # GUIDE never enumerates or deletes unrelated sessions.
        import httpx

        wrapper = self._client._client_wrapper
        base = wrapper.get_base_url().rstrip("/")
        try:
            with httpx.Client(headers={"Authorization": f"Bearer {wrapper._api_key}"}, timeout=10) as http:
                items = http.get(f"{base}/api/v1/trajectories/", params={"size": 100}).json().get("items", [])
                for t in items:
                    if t.get("type") == "agent_platform" and t.get("status") in {"pending", "running", "idle"}:
                        http.delete(f"{base}/api/v1/trajectories/{t['id']}")
        except Exception:  # noqa: BLE001 - best effort
            pass

    def _desktop_channel(self) -> str:
        """One command channel for this Mac, opened once and shared by every session of this process.

        Opening a channel per session costs ~5 s, gets rate-limited, and leaves orphans when the process dies.
        """
        from hai_agents_local.desktop import PyautoguiDesktopBridge
        from hai_agents_local.manager import ensure_bridges, serving_bridges

        wrapper = self._client._client_wrapper
        if self._desktop_session_id is not None and not self._channel_healthy(self._desktop_session_id):
            self._desktop_session_id = None  # stale: the bridge died or the platform closed the channel
        if self._desktop_session_id is None:
            bridge_type = ReadOnlyDesktopBridge if getattr(self, "observe_only", False) else PyautoguiDesktopBridge
            bridge = bridge_type(
                "user-mac", api_key=wrapper._api_key, base_url=wrapper.get_base_url(),
                max_width=self.screenshot_max_width,
            )
            bridge.preflight()
            ensure_bridges([bridge])
            self._desktop_session_id = bridge.session_id
        return self._desktop_session_id

    def _channel_healthy(self, session_id: str) -> bool:
        """The bridge thread still serves it and the platform still knows the channel as open."""
        import httpx
        from hai_agents_local.manager import serving_bridges

        if not serving_bridges([session_id]):
            return False
        wrapper = self._client._client_wrapper
        try:
            r = httpx.get(f"{wrapper.get_base_url().rstrip('/')}/api/v1/trajectories/{session_id}",
                          headers={"Authorization": f"Bearer {wrapper._api_key}"}, timeout=10)
            return r.status_code == 200 and r.json().get("status") not in {"failed", "completed", "interrupted"}
        except Exception:  # noqa: BLE001 - network blip: keep the channel, the session will tell
            return True

    # ----------------------------------------------------------------- preflight

    def preflight(self) -> None:
        if sys.platform == "darwin":
            from hai_agents_local.desktop import ensure_macos_input_permissions

            try:
                ensure_macos_input_permissions(prompt=True)
            except PermissionError as exc:
                raise PreflightError(str(exc)) from exc

    # ----------------------------------------------------------------- agent specs

    def _agent_spec(self, name: str, instructions: str, lazy: bool = False, fast: bool = False) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "name": _agent_name(name),
            "description": "Customer-success assistant driving the user's own desktop.",
            "model": self.model,
            "instructions": instructions + "\n\n" + RESPONSE_LANGUAGE_INSTRUCTIONS,
            "environments": [
                # host=user_device is what makes the SDK serve this Mac from this process; without it H
                # provisions a cloud desktop and the screen seen by the agent is not the user's.
                {"id": "user-mac", "kind": "desktop", "host": "user_device", "lazy": lazy,
                 "session_id": self._desktop_channel(),
                 "screenshot_max_width": min(self.screenshot_max_width, 1024) if fast else self.screenshot_max_width}
            ],
        }
        if fast:
            spec["reasoning_effort"] = "low"  # guide steps are short observations, not plans
        if getattr(self, "observe_only", False):
            spec["instructions"] += (
                "\nObservation-only GUIDE: only inspect the current screen and explain the next user action. "
                "Never click, type, scroll, use shell or access files. The local bridge rejects these commands. "
                "Ask the user to change the screen and wait for their confirmation."
            )
            # Defense in depth; the local allowlist above is the enforcement.
            spec["environments"][0]["shell"] = False
        return spec

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
        if getattr(self, "observe_only", False):
            return AttemptResult(None, "failed", DeclaredResult(
                outcome="blocked", summary="Observation-only GUIDE cannot take control of the desktop.",
                blocker="Desktop actions are disabled for this session.", blocker_category=Category.environment))
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
        agent = self._agent_spec(f"hcs-guide-{proc.id}",
                                 bound.guide_instructions + "\n\n" + _GUIDANCE_PROGRESSION, fast=True)
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
                try:
                    result, from_index, step_offset = self._turn(handle, from_index, n, on_step, step_offset)
                    raw_answer, status = result.answer, result.status
                    cost = _total_cost(result.events) or cost
                except AnswerValidationError as exc:
                    # The turn is over (session idle); only the answer shape was off. Keep what the agent said
                    # and move the cursor past this turn's events.
                    raw_answer, status = _lenient(GuideAnswer, exc.raw), "idle"
                    ch = handle.changes(from_index=from_index, wait_for_seconds=0)
                    from_index += len((ch.new_events if ch else None) or [])
                if stop_event.is_set() or status in {"interrupted", "failed", "timed_out"}:
                    break
                ans = raw_answer if isinstance(raw_answer, GuideAnswer) else None
                if ans is None:
                    declared = DeclaredResult(outcome="unclear", summary=str(result.answer or ""))
                    break
                subs = ans.steps or [GuideSubStep(instruction=ans.instruction, where=ans.where, why=ans.why,
                                                  target_x=ans.target_x, target_y=ans.target_y,
                                                  kind=ans.kind, done_when=ans.done_when)]
                subs = [x for x in subs if x.instruction] or [GuideSubStep(instruction=ans.instruction or "…")]
                if ans.blocked or ans.last:
                    subs = subs[:1]
                # Later instructions are audio candidates only. A click or page transition can
                # invalidate every remaining target, even if all were visible in the last frame.
                sub = subs[0]
                gs = GuidanceStep(index=len(guidance) + 1, instruction=sub.instruction, where=sub.where or "",
                                  why=sub.why or "", pointer=_guide_target_to_screen(
                                      sub.target_x, sub.target_y, ans.coordinate_system),
                                  kind=sub.kind, done_when=sub.done_when,
                                  prepared_speech=[candidate.instruction for candidate in subs[1:3]],
                                  last=(ans.last or ans.blocked))
                guidance.append(gs)
                reply = on_guidance(gs)  # blocks for an interaction/report, not proof of success
                if ans.blocked:
                    declared = DeclaredResult(outcome="blocked", summary=ans.instruction, blocker=ans.blocker,
                                              steps_taken=[g.instruction for g in guidance])
                    break
                if ans.last:
                    declared = DeclaredResult(outcome="done", summary=ans.instruction,
                                              steps_taken=[g.instruction for g in guidance])
                    break
                if reply is None or stop_event.is_set():
                    break
                did, note = reply
                handle.send_message(_guidance_reply_message(did, note, gs.done_when))
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
        if getattr(self, "observe_only", False):
            return VerifyResult(None, "inconclusive", observed=(
                "Observation-only GUIDE requires visual postcondition checks; autonomous verification is disabled."))
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

    def _grounding(self):
        if not hasattr(self, "_grounder"):
            from .grounding import Grounder

            self._grounder = Grounder()
        return self._grounder

    use_a11y: bool = os.environ.get("HCS_A11Y", "1").lower() not in {"0", "false", "no"}

    def _tree_locate(self, description: str) -> tuple[Located | None, list]:
        """Element from the browser accessibility tree: exact box in milliseconds. (None, ties) when unsure."""
        if not self.use_a11y:
            return None, []
        try:
            from . import a11y

            t0 = time.time()
            best, ties, info = a11y.find(description)
            if info is not None:
                from . import sitemap

                if not getattr(self, "observe_only", False):
                    sitemap.remember(info)
            if best is None or info is None or not info.is_front:
                return None, []
            if best.score < 10:  # only word overlap, no label match: let Holo look
                return None, []
            if ties:
                cands = [best, *ties][:8]
                try:  # text-only pick (~0.6 s): role, label and where it sits on screen
                    sw, sh = __import__("hcs_agent.overlay", fromlist=["screen_size_points"]).screen_size_points()
                    opts = [f"{c.role.replace('AX', '')} '{c.name[:50]}' at {_where(c.center, sw, sh)}" for c in cands]
                    idx = self._grounding().choose(description, opts)
                except Exception:  # noqa: BLE001
                    idx = None
                if idx is None:
                    return None, cands
                pick = cands[idx]
                return Located(True, pick.center, f"tree+pick: {pick.role} '{pick.name[:40]}'", time.time() - t0, pick.box), []
            return Located(True, best.center, f"tree: {best.role} '{best.name[:40]}'", time.time() - t0, best.box), []
        except Exception:  # noqa: BLE001 - the tree is an accelerator, never a blocker
            return None, []

    def page_catalogue(self, bound=None, max_items: int = 90):  # noqa: ARG002 - the mock uses `bound`
        """(PageInfo, [Candidate]) of the browser page in front: the controls a planner may point at.
        None when there is no browser page (or the tree is off)."""
        if not self.use_a11y:
            return None
        try:
            from . import a11y, sitemap

            info = a11y.page()
            if info is None or len(info.elements) <= 1:
                return None
            if not getattr(self, "observe_only", False):
                sitemap.remember(info)
            seen: set[tuple[str, str]] = set()
            items = []
            for e in info.elements:
                if e.role not in (*a11y.INTERACTIVE, "AXHeading"):
                    continue
                key = (e.role, e.name.lower())
                if key in seen or e.frame[2] * e.frame[3] > 500 * 400:
                    continue
                if not a11y.visible_at_point(e):
                    continue
                seen.add(key)
                items.append(e)
                if len(items) >= max_items:
                    break
            return info, items
        except Exception:  # noqa: BLE001
            return None

    def plan_step(self, goal: str, context: str, page: str, candidates: list[str], history: list[str]) -> dict | None:
        try:
            return self._grounding().plan_step(goal, context, page, candidates, history)
        except Exception as exc:  # noqa: BLE001
            return {"done": False, "instruction": "", "why": f"planner error: {exc}", "kind": "info", "target": None}

    def locate(self, description: str, context: str = "") -> Located | None:
        hit, ties = self._tree_locate(description)
        if hit is not None:
            return hit
        try:
            loc = self._grounding().locate(description, context)
        except Exception as exc:  # noqa: BLE001 - grounding is best effort; the caller falls back
            return Located(False, None, f"grounding error: {exc}")
        if ties and loc and loc.found and loc.screen_xy:
            # Several tree elements share the label: Holo decides which one, the tree gives the exact box.
            x, y = loc.screen_xy
            near = min(ties, key=lambda c: (c.center[0] - x) ** 2 + (c.center[1] - y) ** 2)
            if abs(near.center[0] - x) < 80 and abs(near.center[1] - y) < 60:
                return Located(True, near.center, f"tree+holo: {near.role} '{near.name[:40]}'", loc.latency_s, near.box)
        return loc

    def effect_visible(self, expected: str) -> tuple[bool, str]:
        return self._visual_check("effect_visible", expected)

    def screen_matches(self, expected: str, software: str = "") -> tuple[bool, str]:
        if getattr(self, "use_a11y", False):
            try:
                from . import a11y
                ok, where = a11y.screen_check(expected, software)
                if type(ok) is bool and isinstance(where, str) and where.strip():
                    self.last_visual_check = {"check": "screen_matches", "status": "observed", "matched": ok}
                    return ok, f"tree: {where}"
            except Exception:
                pass
        return self._visual_check("screen_matches", expected)

    def _visual_check(self, method: str, expected: str) -> tuple[bool, str]:
        try:
            result = getattr(self._grounding(), method)(expected)
            if (not isinstance(result, tuple) or len(result) != 2 or type(result[0]) is not bool
                    or not isinstance(result[1], str) or not result[1].strip()):
                raise ValueError("Unusable visual check")
        except Exception:
            self.last_visual_check = {"check": method, "status": "unavailable",
                                      "message": "Visual verification unavailable; outcome inconclusive."}
            # An empty description prevents the runner mistaking an unavailable
            # check for another foreground application and waiting indefinitely.
            return False, ""
        self.last_visual_check = {"check": method, "status": "observed", "matched": result[0]}
        return result

    def screenshot(self, path: Path) -> Path | None:
        try:
            from .grounding import grab_screen

            img = grab_screen()
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, format="PNG")
        except Exception:  # noqa: BLE001 - evidence is optional
            return None
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
            pointer, element = None, None
            for r in reqs:
                a = _as_dict(r.get("args"))
                if "x" in a and "y" in a:
                    pointer = _agent_xy_to_screen(a["x"], a["y"])
                    element = a.get("element") or element
            return Step(index=index, attempt=attempt, timestamp=ts, kind="action", summary=summary[:300],
                        detail={"actions": actions, "reasoning": _short(d.get("reasoning_content"), 500),
                                "pointer": pointer, "element": element, "tools": [r.get("tool_name") for r in reqs]})
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


def _guide_target_to_screen(x, y, coordinate_system, *, screen_size=None) -> tuple[int, int] | None:
    """Full-main-display GUIDE target -> overlay points; missing/unknown frames hide the target.

    No pixel/normalized heuristic. This mapping is for uncropped full-display
    captures only; a future cropped/window capture needs its own explicit frame.
    """
    if coordinate_system != "normalized_1000":
        return None
    if any(type(v) not in (int, float) or not 0 <= v <= 1000 or not math.isfinite(v) for v in (x, y)):
        return None
    try:
        if screen_size is None:
            from .overlay import screen_size_points

            screen_size = screen_size_points()
        sw, sh = screen_size
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 1 for v in (sw, sh)):
            return None
        # Each axis has its own scale; Retina backing pixels never enter here.
        return min(round(x * sw / 1000), math.ceil(sw) - 1), min(round(y * sh / 1000), math.ceil(sh) - 1)
    except Exception:
        return None


def _to_screen_points(x: int | None, y: int | None, screenshot_max_width: int) -> tuple[int, int] | None:
    """Screenshot pixel coordinates -> screen points. The screenshot is the screen scaled to max_width."""
    if x is None or y is None:
        return None
    try:
        from .overlay import screen_size_points

        sw, _ = screen_size_points()
    except Exception:  # noqa: BLE001
        return int(x), int(y)
    scale = sw / float(screenshot_max_width) if sw > screenshot_max_width else 1.0
    return int(x * scale), int(y * scale)


def _mouse_position() -> tuple[int, int] | None:
    """Where the agent left the pointer, in screen points (the overlay draws there)."""
    try:
        from .overlay import mouse_position

        x, y = mouse_position()
        return int(x), int(y)
    except Exception:  # noqa: BLE001 - non-macOS or no display
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


def _agent_xy_to_screen(x, y) -> tuple[int, int] | None:
    """Desktop-agent action coordinates (normalised 0-1 of the screen) -> screen points for the overlay."""
    try:
        from .overlay import screen_size_points

        sw, sh = screen_size_points()
        fx, fy = float(x), float(y)
        if fx > 1 or fy > 1:  # defensive: pixel coordinates of a 1280-wide screenshot
            return int(fx * sw / 1280), int(fy * sw / 1280)
        return int(fx * sw), int(fy * sh)
    except Exception:  # noqa: BLE001
        return None


def _where(center: tuple[int, int], sw: float, sh: float) -> str:
    """Coarse position words for a point: 'top left', 'centre', 'bottom right'..."""
    x, y = center
    col = "left" if x < sw / 3 else "right" if x > 2 * sw / 3 else "centre"
    row = "top" if y < sh / 3 else "bottom" if y > 2 * sh / 3 else "middle"
    return f"{row} {col}" if (row, col) != ("middle", "centre") else "centre"


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

    def screen_matches(self, expected: str, software: str = "") -> tuple[bool, str]:
        return True, "[simulated] expected screen displayed"

    def effect_visible(self, expected: str) -> tuple[bool, str]:
        return True, "[simulated] effect visible"

    def page_catalogue(self, bound=None, max_items: int = 90):
        from types import SimpleNamespace

        from .a11y import Candidate

        if bound is not None and self._scenario(bound) != "done":
            return None  # simulate a page that cannot be read: the H agent path (and its blocked outcome) runs
        info = SimpleNamespace(url="https://platform.example/sessions", title="Sessions", is_front=True, elements=[])
        items = [Candidate("AXButton", "New session", (400, 300, 120, 32)), Candidate("AXLink", "Agents", (40, 120, 80, 24)),
                 Candidate("AXHeading", f"[simulated] page state {self._plans}", (40, 60, 300, 24))]  # changes per step
        return info, items

    _plans = 0

    def plan_step(self, goal: str, context: str, page: str, candidates: list[str], history: list[str]) -> dict | None:
        self._plans += 1
        if self._plans >= 3 or len(history) >= 2:
            return {"done": True, "instruction": "", "why": "", "kind": "info", "target": None,
                    "summary": "[simulated] goal reached"}
        return {"done": False, "instruction": f"Click New session ({self._plans})", "why": "It starts a session.",
                "kind": "click", "target": 0}

    def locate(self, description: str, context: str = "") -> Located | None:
        time.sleep(self.step_delay_s)
        self._located = getattr(self, "_located", 0) + 1
        if "CRM app" in description:
            return Located(False, None, "[simulated] pipeline already displayed")
        cx, cy = 400 + 60 * self._located, 300 + 40 * self._located
        return Located(True, (cx, cy), "", 0.01, (cx - 60, cy - 14, 120, 28))

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
