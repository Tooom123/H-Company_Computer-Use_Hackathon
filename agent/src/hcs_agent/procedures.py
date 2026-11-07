"""Procedure definitions: the small, versioned knowledge base for one software and its demo scenarios.

A procedure carries everything the runner needs: objective template, preconditions, allowed and
forbidden actions, H prompt, postcondition checks, attempt cap and escalation rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Literal

import yaml
from pydantic import BaseModel, Field

from .contract import Category, InterventionRequest, Mode, ProposedPlan, SessionType

PROCEDURES_DIR = Path(__file__).parent / "procedures"


class ProcedureParameter(BaseModel):
    name: str
    description: str = ""
    required: bool = True
    default: str | None = None


class PostconditionCheck(BaseModel):
    key: str
    prompt: str


class Postcondition(BaseModel):
    description: str
    checks: list[PostconditionCheck]
    verification_instructions: str


class GuideStepSpec(BaseModel):
    """One scripted step of the guide: what to say, which control to point at, why it matters."""

    instruction: str
    element: str = Field(description="Visual description of the control, for grounding on the screenshot.")
    why: str = ""
    optional: bool = Field(default=False, description="Skip silently when the control is not on screen.")
    kind: Literal["click", "type"] | None = Field(default=None, description="Inferred from the verb when omitted.")

    @property
    def action(self) -> str:
        if self.kind:
            return self.kind
        first = self.instruction.strip().lower().split(" ")[0]
        return "type" if first in {"tape", "écris", "ecris", "saisis", "mets", "entre", "type", "enter", "write", "fill"} else "click"


class EscalationRule(BaseModel):
    when: list[str]
    decision_expected: str
    default_category: Category = Category.unknown


class Procedure(BaseModel):
    id: str
    software: str
    software_version: str | None = None
    session_type: SessionType = SessionType.support
    title: str
    reversible: bool
    max_attempts: int = 1
    max_steps_per_attempt: int = 40
    max_time_s_per_attempt: float = 420
    parameters: list[ProcedureParameter] = Field(default_factory=list)
    preconditions: list[str]
    objective: str
    planned_changes: list[str]
    allowed_actions: list[str]
    forbidden_actions: list[str]
    agent_instructions: str
    guide_steps: list[GuideStepSpec] = Field(default_factory=list)
    postcondition: Postcondition
    escalation: EscalationRule

    # ------------------------------------------------------------------ templating

    def resolve_parameters(self, given: dict[str, str]) -> dict[str, str]:
        values = {"software_version": self.software_version or "unknown"}
        missing = []
        for p in self.parameters:
            if p.name in given:
                values[p.name] = given[p.name]
            elif p.default is not None:
                values[p.name] = _resolve_default(p.default)
            elif p.required:
                missing.append(p.name)
        if missing:
            raise ValueError(f"Procedure '{self.id}' is missing required parameters: {', '.join(missing)}")
        return values

    def render(self, text: str, values: dict[str, str]) -> str:
        return text.format_map(_SafeDict(values))

    def bound(self, request: InterventionRequest) -> BoundProcedure:
        values = self.resolve_parameters(request.parameters)
        return BoundProcedure(procedure=self, values=values, request=request)


def _resolve_default(default: str) -> str:
    """Defaults like '+7d' become a date relative to today."""
    import re
    from datetime import date, timedelta

    m = re.fullmatch(r"\+(\d+)d", default.strip())
    return (date.today() + timedelta(days=int(m.group(1)))).isoformat() if m else default


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class BoundProcedure(BaseModel):
    """A procedure with its parameters resolved for one request."""

    procedure: Procedure
    values: dict[str, str]
    request: InterventionRequest

    def _r(self, text: str) -> str:
        return self.procedure.render(text, self.values)

    @property
    def objective(self) -> str:
        return self._r(self.procedure.objective)

    @property
    def preconditions(self) -> list[str]:
        return [self._r(x) for x in self.procedure.preconditions]

    @property
    def agent_instructions(self) -> str:
        return self._r(self.procedure.agent_instructions)

    @property
    def postcondition_description(self) -> str:
        return self._r(self.procedure.postcondition.description)

    @property
    def checks(self) -> dict[str, str]:
        return {c.key: self._r(c.prompt) for c in self.procedure.postcondition.checks}

    @property
    def verification_instructions(self) -> str:
        return self._r(self.procedure.postcondition.verification_instructions)

    @property
    def decision_expected(self) -> str:
        return self._r(self.procedure.escalation.decision_expected)

    @property
    def guide(self) -> bool:
        return self.request.mode is Mode.guide

    def guide_script(self) -> list[GuideStepSpec]:
        return [GuideStepSpec(instruction=self._r(x.instruction), element=self._r(x.element), why=self._r(x.why),
                              optional=x.optional, kind=x.kind) for x in self.procedure.guide_steps]

    @property
    def guide_instructions(self) -> str:
        return GUIDE_INSTRUCTIONS + "\n\nReference procedure (what the user must end up doing):\n" + self.agent_instructions

    def plan(self) -> ProposedPlan:
        p = self.procedure
        role = self.request.role or "user"
        objective_lc = self.objective[0].lower() + self.objective[1:]
        if self.guide:
            explanation = (
                f"As a {role}, you asked: \"{self.request.goal}\". "
                f"I will guide you step by step to {objective_lc} "
                "I will explain each step and point at the control on your screen; you perform the clicks. "
                "I will not change anything myself."
            )
            allowed = ["Move the mouse pointer to show where a control is.",
                       "Read the screen to explain what is displayed."]
            forbidden = ["Clicking, typing or changing anything in the software."] + \
                        [self._r(x) for x in p.forbidden_actions]
        else:
            explanation = (
                f"As a {role}, you asked: \"{self.request.goal}\". "
                f"I will {objective_lc} "
                f"This change is {'reversible' if p.reversible else 'NOT reversible'}. "
                f"I will stop and hand over to support if I cannot complete it within {p.max_attempts} attempt(s)."
            )
            allowed = [self._r(x) for x in p.allowed_actions]
            forbidden = [self._r(x) for x in p.forbidden_actions]
        return ProposedPlan(
            objective=self.objective,
            planned_changes=[self._r(x) for x in p.planned_changes],
            allowed_actions=allowed,
            forbidden_actions=forbidden,
            reversible=p.reversible,
            max_attempts=p.max_attempts,
            explanation=explanation,
            mode=self.request.mode,
        )

    def task_message(self, scope_note: str | None = None, previous_failure: str | None = None) -> str:
        plan = self.plan()
        parts = [
            f"User role: {self.request.role or 'not specified'}.",
            f"User goal: {self.request.goal}",
            f"Task: {self.objective}",
            "Allowed actions:\n- " + "\n- ".join(plan.allowed_actions),
            "Forbidden actions (never do these):\n- " + "\n- ".join(plan.forbidden_actions),
        ]
        if self.request.symptom:
            parts.insert(2, f"Reported symptom: {self.request.symptom}")
        if scope_note:
            parts.append(f"Additional constraint from the user: {scope_note}")
        if previous_failure:
            parts.append(f"A previous attempt did not satisfy the expected result: {previous_failure}")
        if self.guide:
            parts.append(
                "Start now: look at the screen, point at the first control the user must use, and answer with "
                "the first step only (instruction, where, why, last=false)."
            )
        else:
            parts.append(
                "When finished, answer with: result (done / blocked / unclear), a one-paragraph summary, "
                "the exact blocker text if blocked, and the list of steps you actually performed."
            )
        return "\n\n".join(parts)


GUIDE_INSTRUCTIONS = """\
You are a patient support guide sitting next to the user. The user performs every action; you only
explain and point. Your answer is drawn on the user's screen as a pencil note: a circle at
(target_x, target_y) and your `instruction` next to it.
Rules:
- NEVER click, type, scroll, press keys, move the mouse or change anything. Only observe and answer.
- Work one step at a time. Look at the screen, then answer with exactly one step.
  `instruction`: one short line, max 12 words, imperative ("Click the CRM app icon").
  `why`: one or two sentences for a first-week user.
  `target_x`/`target_y`: the pixel position of the control in the screenshot you are looking at.
- If the expected software is not visible (another app or tab is in front), do NOT hunt for it: answer
  with target null and an instruction like "Bring the Odoo tab to the front", nothing else.
- After each answer the user tells you they did the step (or could not). Look at the screen again before
  the next step; adapt to what is actually displayed.
- When several consecutive steps use controls that are ALL visible right now (e.g. type a value, then click
  the button next to it), return them together in `steps` (max 3) so the user is not kept waiting. Never
  include a step whose control is not yet on screen.
- Set last=true only when the goal is visibly achieved on screen.
- If the user cannot proceed because of an error or missing permission, quote the message you see in
  `blocker` and set last=true, blocked=true.
- If you are not sure what a menu or a field is for, or where a feature lives, call `lookup_docs` and
  put the answer in `why`, briefly. Say "I am not sure" rather than guessing.
"""


# ---------------------------------------------------------------------- registry


def load_procedure(path: Path) -> Procedure:
    return Procedure.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def iter_procedures(directory: Path = PROCEDURES_DIR) -> Iterator[Procedure]:
    for path in sorted(directory.glob("*.yaml")):
        yield load_procedure(path)


class ProcedureRegistry:
    def __init__(self, directory: Path = PROCEDURES_DIR) -> None:
        self._by_id = {p.id: p for p in iter_procedures(directory)}

    def get(self, procedure_id: str) -> Procedure:
        try:
            return self._by_id[procedure_id]
        except KeyError:
            raise KeyError(f"Unknown procedure '{procedure_id}'. Known: {sorted(self._by_id)}") from None

    def for_request(self, request: InterventionRequest) -> Procedure:
        if request.procedure_id:
            return self.get(request.procedure_id)
        candidates = [p for p in self._by_id.values() if p.software == request.software]
        if len(candidates) != 1:
            raise ValueError(
                f"Cannot pick a procedure for software '{request.software}' without procedure_id "
                f"(candidates: {[p.id for p in candidates]})."
            )
        return candidates[0]

    def all(self) -> list[Procedure]:
        return list(self._by_id.values())
