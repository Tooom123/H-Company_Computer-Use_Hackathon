"""Shared contract between the user app (Electron), the H agent (this package) and the support backend.

Everything that crosses a boundary is defined here. Fields deliberately separate:
- what the user declared (role, goal, feedback),
- what the agent declared (claimed success),
- what was observed (postcondition verification).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------- enums


class SessionType(str, Enum):
    onboarding = "onboarding"
    configuration = "configuration"
    support = "support"
    discovery = "discovery"
    feedback = "feedback"


class Category(str, Enum):
    usage = "usage"
    configuration = "configuration"
    permissions = "permissions"
    data = "data"
    suspected_product_defect = "suspected_product_defect"
    environment = "environment"
    agent_failure = "agent_failure"
    unknown = "unknown"


class CaseStatus(str, Enum):
    resolved = "resolved"
    workaround = "workaround"
    escalated = "escalated"
    abandoned = "abandoned"


class Mode(str, Enum):
    """`act`: the agent performs the steps. `guide`: the agent explains and points, the user performs."""

    act = "act"
    guide = "guide"


class State(str, Enum):
    """Intervention state machine."""

    created = "created"
    preflight_failed = "preflight_failed"
    awaiting_approval = "awaiting_approval"
    running = "running"
    awaiting_user = "awaiting_user"
    verifying = "verifying"
    stopping = "stopping"
    stopped = "stopped"
    resolved = "resolved"
    escalated = "escalated"
    failed = "failed"

    @property
    def terminal(self) -> bool:
        return self in {State.preflight_failed, State.stopped, State.resolved, State.escalated, State.failed}


# --------------------------------------------------------------------------- request and commands


class InterventionRequest(BaseModel):
    """A help request, as sent by the user app."""

    session_id: str = Field(default_factory=lambda: new_id("sess"))
    software: str = Field(description="Target software, e.g. 'odoo'.")
    software_version: str | None = None
    role: str | None = Field(default=None, description="Role declared by the user.")
    goal: str = Field(description="Goal or problem described by the user.")
    symptom: str | None = None
    procedure_id: str | None = Field(default=None, description="Procedure to use; otherwise picked by software.")
    parameters: dict[str, str] = Field(default_factory=dict, description="Values injected into the procedure.")
    session_type: SessionType = SessionType.support
    mode: Mode = Field(default=Mode.act, description="act: agent does it; guide: agent explains, user does it.")
    autonomy: int = Field(default=1, ge=0, le=2,
                          description="0: show only, never take over; 1: guide, take over when stuck; 2: do it, narrate.")
    user_id: str | None = None
    client_id: str | None = None


class ApproveCommand(BaseModel):
    """The user approves (or declines) the proposed scope."""

    approved: bool = True
    scope_note: str | None = Field(default=None, description="Extra constraint or precision added by the user.")


class StopCommand(BaseModel):
    reason: str | None = None


class NextCommand(BaseModel):
    """Guide mode: the user reports on the step they were asked to perform."""

    done: bool = True
    note: str | None = Field(default=None, description="What the user saw, or why they could not do it.")


class AutonomyCommand(BaseModel):
    """Live change of the help level (the Magnet): 0 show only, 1 help when stuck, 2 do it and narrate."""

    level: int = Field(ge=0, le=2)


class FeedbackCommand(BaseModel):
    """Free-form user feedback. Never inferred by the agent."""

    useful: bool | None = None
    comment: str | None = None
    allow_screenshots_to_support: bool = False


# --------------------------------------------------------------------------- proposed plan
class DocSource(BaseModel):
    name: str
    url: str
    snippet: str = ""



class ProposedPlan(BaseModel):
    """What the agent proposes to do. Must be approved before any action."""

    objective: str
    planned_changes: list[str]
    allowed_actions: list[str]
    forbidden_actions: list[str]
    reversible: bool
    max_attempts: int
    explanation: str = Field(description="Explanation adapted to the declared role.")
    mode: Mode = Mode.act
    documentation: str | None = Field(default=None, description="Sourced summary from the vendor documentation.")
    sources: list[DocSource] = Field(default_factory=list)
    observes: str = "Screenshots of the main display are sent to H during the intervention."


class Annotation(BaseModel):
    """An extra mark drawn on screen with a step: a box around a zone, a circled element, a label."""

    shape: Literal["circle", "box", "underline", "label"] = "label"
    text: str = ""
    pointer: tuple[int, int] | None = None
    size: tuple[int, int] | None = None
    box: tuple[int, int, int, int] | None = Field(default=None, description="Element bounds (x, y, w, h) in screen points.")


class GuidanceStep(BaseModel):
    """One step explained to the user in guide mode."""

    index: int
    instruction: str = Field(description="What the user should do now, in plain words.")
    where: str = Field(default="", description="Where the control is on screen.")
    why: str = Field(default="", description="What this step achieves.")
    pointer: tuple[int, int] | None = Field(default=None, description="Screen coordinates the agent pointed at.")
    box: tuple[int, int, int, int] | None = Field(default=None, description="Element bounds (x, y, w, h) in screen points.")
    box_exact: bool = Field(default=False, description="True when the box comes from the accessibility tree "
                                                       "(pixel-exact), False when estimated from a screenshot.")
    kind: Literal["click", "type", "key", "info", "wait"] = Field(
        default="click",
        description="click / type / key: act; info: read, moves on by itself; wait: the agent polls the screen.")
    done_when: str | None = Field(default=None,
        description="Expected visible result to check after an interaction; not an observed or verified outcome.")
    prepared_speech: list[str] = Field(default_factory=list, max_length=2,
        description="At most two tentative next instructions for audio preparation only. Never display or advance "
                    "to these without a fresh observation and guidance response.")
    annotations: list[Annotation] = Field(default_factory=list)
    last: bool = False
    shown_at: datetime | None = None
    done_s: float | None = Field(default=None, description="Seconds the user took to do the step.")


# --------------------------------------------------------------------------- events


EventType = Literal[
    "state_changed",
    "plan_proposed",
    "step",
    "attempt_started",
    "attempt_finished",
    "verification",
    "guidance",
    "knowledge",
    "needs_human",
    "stopped",
    "finished",
    "error",
]


class AgentEvent(BaseModel):
    """Event emitted by the agent towards the app and the backend."""

    event_id: str = Field(default_factory=lambda: new_id("evt"))
    session_id: str
    type: EventType
    timestamp: datetime = Field(default_factory=_now)
    state: State
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    simulated: bool = Field(default=False, description="True when produced by the mock backend, never by H.")


# --------------------------------------------------------------------------- report


class Step(BaseModel):
    index: int
    attempt: int
    timestamp: datetime
    kind: Literal["observation", "action", "message", "error", "answer"]
    summary: str
    detail: dict[str, Any] = Field(default_factory=dict)


class DeclaredResult(BaseModel):
    """What the H agent claims it did. Not proof."""

    outcome: Literal["done", "blocked", "unclear", "not_run"] = "not_run"
    summary: str = ""
    blocker: str | None = None
    blocker_category: Category | None = None
    steps_taken: list[str] = Field(default_factory=list)


class Verification(BaseModel):
    """Postcondition observed after the intervention, independent from the agent's claim."""

    performed: bool = False
    satisfied: bool | None = None
    postcondition: str
    observed: str = ""
    checks: dict[str, bool] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    user_confirmed: bool | None = None


class Evidence(BaseModel):
    ref: str
    kind: Literal["screenshot", "h_session", "text"]
    description: str
    path: str | None = None
    url: str | None = None
    shareable_with_support: bool = False


class KnowledgeNote(BaseModel):
    """A sourced documentation lookup (Linkup). Provided information, distinct from observation."""

    purpose: Literal["explain", "agent_lookup", "blocker"]
    query: str
    answer: str
    sources: list[DocSource] = Field(default_factory=list)
    simulated: bool = False


class Escalation(BaseModel):
    """Case file handed to support when the goal was not reached."""

    blocked_on: str
    attempts: int
    decision_expected: str
    suggested_next_step: str | None = None


class Timings(BaseModel):
    started_at: datetime | None = None
    approved_at: datetime | None = None
    finished_at: datetime | None = None
    stop_requested_at: datetime | None = None
    stop_effective_at: datetime | None = None

    @property
    def stop_latency_s(self) -> float | None:
        if self.stop_requested_at and self.stop_effective_at:
            return (self.stop_effective_at - self.stop_requested_at).total_seconds()
        return None

    @property
    def duration_s(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class InterventionReport(BaseModel):
    """Structured report of one intervention, readable by support and groupable by the dashboard."""

    case_id: str = Field(default_factory=lambda: new_id("case"))
    session_id: str
    software: str
    software_version: str | None
    os: str
    role: str | None
    session_type: SessionType
    goal: str
    symptom: str | None
    mode: Mode = Mode.act
    autonomy: int = 1
    takeover: bool = False
    procedure_id: str | None
    approved_scope: ProposedPlan | None
    guidance: list[GuidanceStep] = Field(default_factory=list)
    knowledge: list[KnowledgeNote] = Field(default_factory=list)
    scope_note: str | None = None
    steps: list[Step]
    declared: DeclaredResult
    verification: Verification
    status: CaseStatus
    category: Category
    suspected_cause: str | None
    needs_human: bool
    escalation: Escalation | None
    evidence: list[Evidence]
    feedback: FeedbackCommand | None
    h_session_ids: list[str]
    timings: Timings
    cost_usd: float | None = None
    simulated: bool = False
    demo_data: bool = True

    def to_support_summary(self) -> dict[str, Any]:
        """Compact view used by the dashboard for grouping."""
        return {
            "case_id": self.case_id,
            "software": self.software,
            "procedure_id": self.procedure_id,
            "category": self.category.value,
            "status": self.status.value,
            "mode": self.mode.value,
            "goal": self.goal,
            "symptom": self.symptom,
            "blocked_on": self.escalation.blocked_on if self.escalation else None,
            "verified": self.verification.satisfied,
            "declared": self.declared.outcome,
            "needs_human": self.needs_human,
            "autonomy": self.autonomy,
            "takeover": self.takeover,
            "guided_steps": len(self.guidance),
            "duration_s": round(self.timings.duration_s, 1) if self.timings.duration_s is not None else None,
            "cost_usd": self.cost_usd,
            "simulated": self.simulated,
        }
