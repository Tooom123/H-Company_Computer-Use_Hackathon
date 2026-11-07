"""Procedure definitions: the small, versioned knowledge base for one software and its demo scenarios.

A procedure carries everything the runner needs: objective template, preconditions, allowed and
forbidden actions, H prompt, postcondition checks, attempt cap and escalation rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import yaml
from pydantic import BaseModel, Field

from .contract import Category, InterventionRequest, ProposedPlan, SessionType

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
                values[p.name] = p.default
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

    def plan(self) -> ProposedPlan:
        p = self.procedure
        role = self.request.role or "user"
        explanation = (
            f"As a {role}, you asked: \"{self.request.goal}\". "
            f"I will {self.objective[0].lower() + self.objective[1:]} "
            f"This change is {'reversible' if p.reversible else 'NOT reversible'}. "
            f"I will stop and hand over to support if I cannot complete it within {p.max_attempts} attempt(s)."
        )
        return ProposedPlan(
            objective=self.objective,
            planned_changes=[self._r(x) for x in p.planned_changes],
            allowed_actions=[self._r(x) for x in p.allowed_actions],
            forbidden_actions=[self._r(x) for x in p.forbidden_actions],
            reversible=p.reversible,
            max_attempts=p.max_attempts,
            explanation=explanation,
        )

    def task_message(self, scope_note: str | None = None, previous_failure: str | None = None) -> str:
        parts = [
            f"User role: {self.request.role or 'not specified'}.",
            f"User goal: {self.request.goal}",
            f"Task: {self.objective}",
            "Allowed actions:\n- " + "\n- ".join(self.plan().allowed_actions),
            "Forbidden actions (never do these):\n- " + "\n- ".join(self.plan().forbidden_actions),
        ]
        if self.request.symptom:
            parts.insert(2, f"Reported symptom: {self.request.symptom}")
        if scope_note:
            parts.append(f"Additional constraint from the user: {scope_note}")
        if previous_failure:
            parts.append(f"A previous attempt did not satisfy the expected result: {previous_failure}")
        parts.append(
            "When finished, answer with: outcome (done / blocked / unclear), a one-paragraph summary, "
            "the exact blocker text if blocked, and the list of steps you actually performed."
        )
        return "\n\n".join(parts)


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
