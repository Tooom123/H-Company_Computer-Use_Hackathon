"""Intervention runner: the state machine that turns a request into a verified result or an escalation.

Flow: created -> (preflight) -> awaiting_approval -> running -> verifying -> resolved | escalated
                                                   \\-> stopping -> stopped (at any time)

Guarantees enforced here, not in the prompt:
- nothing is sent to H before `approve(approved=True)`;
- `stop()` blocks any new H command locally, asks H to cancel, and measures the delay;
- the agent's declared outcome never decides the case status; the observed verification does;
- the attempt cap comes from the procedure; past it, the case is escalated with a decision for support.
"""

from __future__ import annotations

import platform
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .backend import AttemptResult, Backend, PreflightError, VerifyResult
from .contract import (
    AgentEvent,
    ApproveCommand,
    CaseStatus,
    Category,
    DeclaredResult,
    Escalation,
    Evidence,
    FeedbackCommand,
    InterventionReport,
    InterventionRequest,
    ProposedPlan,
    State,
    Step,
    StopCommand,
    Timings,
    Verification,
)
from .procedures import BoundProcedure, ProcedureRegistry

EventSink = Callable[[AgentEvent], None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Intervention:
    """One help request, from creation to report. Thread-safe for approve/stop from another thread."""

    def __init__(
        self,
        request: InterventionRequest,
        backend: Backend,
        registry: ProcedureRegistry,
        sink: EventSink,
        runs_dir: Path = Path("runs"),
    ) -> None:
        self.request = request
        self.backend = backend
        self.sink = sink
        self.runs_dir = runs_dir / request.session_id
        self.state = State.created
        self.plan: ProposedPlan | None = None
        self.scope_note: str | None = None
        self.steps: list[Step] = []
        self.evidence: list[Evidence] = []
        self.h_session_ids: list[str] = []
        self.declared = DeclaredResult()
        self.verification: Verification | None = None
        self.feedback: FeedbackCommand | None = None
        self.report: InterventionReport | None = None
        self.timings = Timings(started_at=_now())
        self.cost_usd = 0.0
        self.attempts = 0
        self.error: str | None = None
        self._bound: BoundProcedure | None = None
        self._stop = threading.Event()
        self._approval = threading.Event()
        self._approved: bool | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        try:
            self._bound = registry.for_request(request).bound(request)
        except (KeyError, ValueError) as exc:
            self.error = str(exc)

    # ------------------------------------------------------------------ events

    def _emit(self, type_: str, message: str | None = None, **data) -> None:
        self.sink(AgentEvent(session_id=self.request.session_id, type=type_, state=self.state,
                             message=message, data=data, simulated=self.backend.simulated))

    def _set_state(self, state: State, message: str | None = None) -> None:
        with self._lock:
            if self.state.terminal:
                return
            self.state = state
        self._emit("state_changed", message)

    def _on_step(self, step: Step) -> None:
        step.index = len(self.steps)
        self.steps.append(step)
        self._emit("step", step.summary, step=step.model_dump(mode="json"))

    # ------------------------------------------------------------------ commands

    def start(self) -> None:
        """Preflight the machine and propose the plan. Does not contact H."""
        if self.error or self._bound is None:
            self._set_state(State.failed, self.error)
            self._finish()
            return
        try:
            self.backend.preflight()
        except PreflightError as exc:
            self._set_state(State.preflight_failed, str(exc))
            self.error = str(exc)
            self._finish()
            return
        self.plan = self._bound.plan()
        self._set_state(State.awaiting_approval, "Waiting for the user to approve the proposed scope.")
        self._emit("plan_proposed", self.plan.explanation, plan=self.plan.model_dump(),
                   preconditions=self._bound.preconditions)
        self._thread = threading.Thread(target=self._run, name=f"intervention-{self.request.session_id}", daemon=True)
        self._thread.start()

    def approve(self, cmd: ApproveCommand) -> None:
        if self.state is not State.awaiting_approval:
            raise RuntimeError(f"Cannot approve in state {self.state.value}")
        self._approved = cmd.approved
        self.scope_note = cmd.scope_note
        self.timings.approved_at = _now()
        self._approval.set()

    def stop(self, cmd: StopCommand | None = None) -> None:
        """Local gate first (no new command leaves this process), then H cancel through the backend."""
        if self.state.terminal:
            return
        self.timings.stop_requested_at = _now()
        self._set_state(State.stopping, (cmd.reason if cmd else None) or "Stop requested by the user.")
        self._stop.set()
        self._approval.set()  # unblock a pending approval wait

    def add_feedback(self, fb: FeedbackCommand) -> None:
        self.feedback = fb
        if self.report is not None:
            self.report.feedback = fb
            for ev in self.report.evidence:
                if ev.kind == "screenshot":
                    ev.shareable_with_support = fb.allow_screenshots_to_support
            self._save_report()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------------ main loop

    def _run(self) -> None:
        assert self._bound is not None
        bound, proc = self._bound, self._bound.procedure
        self._approval.wait()
        if self._stop.is_set():
            return self._finish_stopped()
        if not self._approved:
            self._set_state(State.stopped, "The user declined the proposed scope.")
            return self._finish(status=CaseStatus.abandoned)

        previous_failure: str | None = None
        last_attempt: AttemptResult | None = None
        verify: VerifyResult | None = None
        self._set_state(State.running, "Intervention approved. Working in the software now.")
        self._snapshot("before", "Screen before the intervention")

        for attempt in range(1, proc.max_attempts + 1):
            if self._stop.is_set():
                return self._finish_stopped()
            self.attempts = attempt
            self._emit("attempt_started", f"Attempt {attempt}/{proc.max_attempts}", attempt=attempt)
            task = bound.task_message(self.scope_note, previous_failure)
            last_attempt = self.backend.run_attempt(bound, task, attempt, self._on_step, self._stop)
            self._record_attempt(last_attempt)
            self._emit("attempt_finished", last_attempt.declared.summary or last_attempt.status,
                       attempt=attempt, h_status=last_attempt.status, declared=last_attempt.declared.model_dump())
            if self._stop.is_set():
                return self._finish_stopped()
            if last_attempt.declared.outcome == "blocked":
                break  # escalation rule: a recognised limit is not retried

            self._set_state(State.verifying, "Checking the result in the software.")
            verify = self.backend.verify(bound, self._on_step, self._stop)
            self._record_verify(verify)
            if self._stop.is_set():
                return self._finish_stopped()
            if verify.checks and all(verify.checks.values()):
                self._snapshot("after", "Screen after verification")
                self._set_state(State.resolved, "Result verified in the software.")
                return self._finish(status=CaseStatus.resolved)
            failed = [k for k, v in verify.checks.items() if not v] or ["verification unavailable"]
            previous_failure = f"checks not satisfied: {', '.join(failed)}. Observed: {verify.observed}"
            self._set_state(State.running, f"Not verified after attempt {attempt}.")

        self._snapshot("after", "Screen at escalation")
        self._set_state(State.escalated, "The goal could not be verified. Handing over to support.")
        self._emit("needs_human", self._bound.decision_expected)
        self._finish(status=CaseStatus.escalated, last_attempt=last_attempt, verify=verify)

    # ------------------------------------------------------------------ bookkeeping

    def _record_attempt(self, res: AttemptResult) -> None:
        if res.h_session_id:
            self.h_session_ids.append(res.h_session_id)
            self.evidence.append(Evidence(ref=res.h_session_id, kind="h_session",
                                          description="H session trace (steps and screenshots)", url=res.agent_view_url))
        if res.cost_usd:
            self.cost_usd += res.cost_usd
        self.declared = res.declared
        if res.error:
            self.error = res.error

    def _record_verify(self, res: VerifyResult) -> None:
        assert self._bound is not None
        if res.h_session_id:
            self.h_session_ids.append(res.h_session_id)
        if res.cost_usd:
            self.cost_usd += res.cost_usd
        self.verification = Verification(
            performed=res.status not in {"interrupted", "failed"} or bool(res.checks),
            satisfied=bool(res.checks) and all(res.checks.values()),
            postcondition=self._bound.postcondition_description,
            observed=res.observed or (res.error or ""),
            checks=res.checks,
            evidence_refs=[res.h_session_id] if res.h_session_id else [],
        )
        self._emit("verification", res.observed, checks=res.checks, satisfied=self.verification.satisfied)

    def _snapshot(self, tag: str, description: str) -> None:
        path = self.backend.screenshot(self.runs_dir / f"{tag}.png")
        if path:
            self.evidence.append(Evidence(ref=f"screenshot:{tag}", kind="screenshot", description=description,
                                          path=str(path)))

    def _finish_stopped(self) -> None:
        self.timings.stop_effective_at = _now()
        with self._lock:
            self.state = State.stopped
        self._emit("stopped", "Intervention stopped. Changes already made are not reverted.",
                   stop_latency_s=self.timings.stop_latency_s)
        self._finish(status=CaseStatus.abandoned)

    def _finish(self, status: CaseStatus | None = None, last_attempt: AttemptResult | None = None,
                verify: VerifyResult | None = None) -> None:
        self.timings.finished_at = _now()
        self.report = self._build_report(status, last_attempt, verify)
        self._save_report()
        self._emit("finished", f"Case {self.report.case_id}: {self.report.status.value}",
                   report=self.report.model_dump(mode="json"))

    # ------------------------------------------------------------------ report

    def _build_report(self, status: CaseStatus | None, last_attempt: AttemptResult | None,
                      verify: VerifyResult | None) -> InterventionReport:
        bound = self._bound
        proc = bound.procedure if bound else None
        verification = self.verification or Verification(
            postcondition=bound.postcondition_description if bound else "", performed=False)
        status = status or (CaseStatus.abandoned if self.state in {State.stopped, State.preflight_failed, State.failed}
                            else CaseStatus.escalated)
        category, cause = self._classify(status, verification)
        needs_human = status is CaseStatus.escalated or self.state in {State.preflight_failed, State.failed}
        escalation = None
        if needs_human:
            escalation = Escalation(
                blocked_on=self.declared.blocker or self.error or verification.observed or "goal not verified",
                attempts=self.attempts,
                decision_expected=(bound.decision_expected if bound and status is CaseStatus.escalated
                                   else "Check the environment or permissions on the user's machine."),
                suggested_next_step=self._suggest(category),
            )
        return InterventionReport(
            session_id=self.request.session_id,
            software=self.request.software,
            software_version=self.request.software_version or (proc.software_version if proc else None),
            os=f"{platform.system()} {platform.mac_ver()[0] or platform.release()}",
            role=self.request.role,
            session_type=self.request.session_type,
            goal=self.request.goal,
            symptom=self.request.symptom,
            procedure_id=proc.id if proc else self.request.procedure_id,
            approved_scope=self.plan if self._approved else None,
            scope_note=self.scope_note,
            steps=self.steps,
            declared=self.declared,
            verification=verification,
            status=status,
            category=category,
            suspected_cause=cause,
            needs_human=needs_human,
            escalation=escalation,
            evidence=self.evidence,
            feedback=self.feedback,
            h_session_ids=self.h_session_ids,
            timings=self.timings,
            cost_usd=self.cost_usd,
            simulated=self.backend.simulated,
        )

    def _classify(self, status: CaseStatus, verification: Verification) -> tuple[Category, str | None]:
        """Category for grouping. Rule-based and conservative; `unknown` beats a guess."""
        if self.state is State.preflight_failed:
            return Category.environment, "The assistant could not drive the machine (macOS permissions)."
        if status is CaseStatus.resolved:
            return Category.usage, None
        if self.declared.outcome == "blocked":
            cat = self.declared.blocker_category or (self._bound.procedure.escalation.default_category
                                                     if self._bound else Category.unknown)
            return cat, self.declared.blocker
        if self.error:
            return Category.agent_failure, self.error
        if self.declared.outcome == "done" and verification.performed and verification.satisfied is False:
            return Category.unknown, "The agent declared success but the expected result was not observed."
        if status is CaseStatus.abandoned:
            return Category.unknown, None
        return (self._bound.procedure.escalation.default_category if self._bound else Category.unknown), None

    @staticmethod
    def _suggest(category: Category) -> str | None:
        return {
            Category.permissions: "Grant or confirm the user's access rights, then let the user retry.",
            Category.environment: "Check macOS Screen Recording / Accessibility grants for the assistant.",
            Category.data: "Check that the record exists with the expected name.",
            Category.agent_failure: "Review the H session trace; retry once the agent issue is understood.",
        }.get(category)

    def _save_report(self) -> None:
        if self.report is None:
            return
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        (self.runs_dir / "report.json").write_text(self.report.model_dump_json(indent=2), encoding="utf-8")
