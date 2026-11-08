"""Procedure definitions: the small, versioned knowledge base for one software and its demo scenarios.

A procedure carries everything the runner needs: objective template, preconditions, allowed and
forbidden actions, H prompt, postcondition checks, attempt cap and escalation rule.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit
from pathlib import Path
from typing import Iterator, Literal

import yaml
from pydantic import BaseModel, Field

from .contract import Category, InterventionRequest, Mode, ProposedPlan, SessionType

PROCEDURES_DIR = Path(__file__).parent / "procedures"

RESPONSE_LANGUAGE_INSTRUCTIONS = (
    "Response language: English. Write every instruction, explanation, clarification, annotation, "
    "spoken sentence, blocker explanation and final answer in English, even when the user's question "
    "or the conversation history is in French or requests another response language. Preserve exact "
    "UI labels, quotations, code and the user's original request when citing them; explain them in English. "
    "Do not translate or rewrite the stored user question. This language rule does not authorize any action."
)

COACHING_STYLE_INSTRUCTIONS = (
    "Speak like a helpful colleague sitting beside the user: warm, calm, direct and concise. "
    "Use natural contractions and lead with the useful fact or next action, not a status label. "
    "For example: 'Here's the section you need' followed by the observed heading and its relevance. "
    "Keep the user-facing final answer to at most two short sentences and 45 words. "
    "Paraphrase the useful point instead of quoting an entire documentation paragraph or repeating it as an explanation. "
    "Avoid 'Done:', 'Task completed', generic 'I hope it helps', repeated congratulations and filler. "
    "A friendly tone must not imply success or verification without evidence. Keep exact UI labels; "
    "say what remains uncertain. Never add a follow-up question merely to prolong a completed task."
)

PRODUCT_COACHING_SCOPE = (
    "You are a coach for the selected software, not a general-purpose question-answering assistant. "
    "Keep every answer connected to this product's visible interface, records, or supplied documentation. "
    "A welcome, introduction, 'show me around' or first-time request normally concerns the selected product. "
    "Spoken requests may contain transcription errors. If an unexpected place, person or product name "
    "makes the request ambiguous and has no support in the current interface or product documentation, "
    "ask ONE clarification of at most 15 words naming the selected product, then stop without taking actions. "
    "For 'welcome to' followed by an unsupported name, ask 'Did you mean a quick tour of [selected product]?' "
    "Do not search for the uncertain name or offer an unrelated general-knowledge alternative. "
    "Do not improvise an unrelated general-knowledge answer or silently replace the recorded words. "
    "A named customer, project or other record actually visible in the product is valid context; do not "
    "reject it merely because its name also denotes a place. If the user explicitly asks an unrelated "
    "question, briefly offer help with the selected software instead. Current product identity comes "
    "from the foreground context, never from the transcript or a previous goal."
)


COACHING_ORIGINS = {
    "comfyui": {"cloud.comfy.org", "docs.comfy.org"},
    "capcut": {"www.capcut.com", "capcut.com"},
    "h-company": {"hub.hcompany.ai", "platform.hcompany.ai"},
    "cognition": {"app.devin.ai", "docs.devin.ai", "cognition.ai", "www.cognition.ai", "cognition.com", "www.cognition.com"},
}


def coaching_page_allowed(software: str, url: str, *, native: bool = False,
                          bundle_id: str | None = None, is_front: bool = True) -> bool:
    """Fail closed before sending AX labels from sponsor pilots to the model."""
    if native:
        from .a11y import NATIVE_APPLICATIONS
        if software != "cognition" or bundle_id not in NATIVE_APPLICATIONS or not is_front:
            return False
        # Native identity is explicit evidence of the app, not evidence of a web origin. Local Electron
        # resource URLs may be observed but are never sent to the planner. Real web URLs keep origin rules.
        if not url:
            return True
        try:
            internal = urlsplit(url)
            if internal.scheme in {"file", "vscode-file", "vscode-webview", "devin"}:
                return not internal.username and not internal.password
        except (TypeError, ValueError):
            return False
    allowed = COACHING_ORIGINS.get(software)
    if allowed is None:
        return True
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password
                or parsed.port not in (None, 443)):
            return False
        path = unquote(parsed.path).lower()
        restricted = r"(?:^|/)(?:auth|login|signin|sign-in|credentials|secrets|vaults?|api-keys?|tokens?|billing|payments?|security)(?:/|$)"
        # Documentation may describe these features; account pages must never expose their values.
        return parsed.hostname in {"hub.hcompany.ai", "docs.devin.ai", "cognition.ai", "www.cognition.ai", "cognition.com", "www.cognition.com", "docs.comfy.org"} or not re.search(restricted, path)
    except (TypeError, ValueError):
        return False


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


class AnnotationSpec(BaseModel):
    """Extra mark drawn with a step: explains a zone or an element around the main control."""

    element: str = Field(description="Visual description for grounding.")
    text: str = ""
    shape: Literal["circle", "box", "underline", "label"] = "label"
    size: tuple[int, int] | None = Field(default=None, description="Box size in screen points.")


class GuideStepSpec(BaseModel):
    """One scripted step of the guide: what to say, which control to point at, why it matters."""

    instruction: str
    element: str | None = Field(default=None, description="Visual description of the control, for grounding. None for an info step.")
    why: str = ""
    optional: bool = Field(default=False, description="Skip silently when the control is not on screen.")
    kind: Literal["click", "type", "info"] | None = Field(default=None, description="Inferred from the verb when omitted.")
    done_when: str | None = Field(
        default=None, description="What the screen shows once this step is done (checked by Holo). Use it when the "
                                  "next control is already visible before the step, so a stray click cannot advance.")
    annotations: list[AnnotationSpec] = Field(default_factory=list)

    @property
    def action(self) -> str:
        if self.kind:
            return self.kind
        if not self.element:
            return "info"
        first = self.instruction.strip().lower().split(" ")[0]
        return "type" if first in {"tape", "écris", "ecris", "saisis", "mets", "entre", "type", "enter", "write", "fill",
                                   "replace"} else "click"


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
    dynamic_tail: bool = Field(default=False, description="After the scripted steps, keep guiding from the page's "
                                                          "own controls (planner) until the objective is reached — "
                                                          "for flows whose later screens are not scripted (wizards).")
    expected_screen: str = Field(default="", description="What must be displayed before step 1, for the screen check.")
    recovery_steps: list[GuideStepSpec] = Field(
        default_factory=list, description="How to get back to the base screen when the script is lost.")
    postcondition: Postcondition
    escalation: EscalationRule

    # ------------------------------------------------------------------ templating

    def resolve_parameters(self, given: dict[str, str]) -> dict[str, str]:
        from datetime import date

        values = {"software_version": self.software_version or "unknown", "today": date.today().isoformat()}
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
        if self.procedure.id == GENERIC_ID:
            # Generic procedures already contain the resolved user goal and
            # retrieved excerpts. JSON/code braces are data, not format fields.
            return text
        return self.procedure.render(text, self.values)

    @property
    def objective(self) -> str:
        return self._r(self.procedure.objective)

    @property
    def preconditions(self) -> list[str]:
        return [self._r(x) for x in self.procedure.preconditions]

    @property
    def agent_instructions(self) -> str:
        instructions = (self._r(self.procedure.agent_instructions) + "\n\n" + PRODUCT_COACHING_SCOPE
                        + "\n\n" + COACHING_STYLE_INSTRUCTIONS)
        if self.request.software in {"h-company", "hcompany"}:
            instructions += "\n\n" + H_DOCUMENTATION_TABS + "\n\n" + H_DOCUMENTATION_READING
        return instructions

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

    def recovery_script(self) -> list[GuideStepSpec]:
        return [GuideStepSpec(instruction=self._r(x.instruction), element=self._r(x.element) if x.element else None,
                              why=self._r(x.why), optional=x.optional, kind=x.kind,
                              done_when=self._r(x.done_when) if x.done_when else None)
                for x in self.procedure.recovery_steps]

    @property
    def expected_screen(self) -> str:
        return self._r(self.procedure.expected_screen)

    def guide_script(self) -> list[GuideStepSpec]:
        return [GuideStepSpec(instruction=self._r(x.instruction), element=self._r(x.element) if x.element else None,
                              why=self._r(x.why), optional=x.optional, kind=x.kind,
                              done_when=self._r(x.done_when) if x.done_when else None,
                              annotations=[AnnotationSpec(element=self._r(a.element), text=self._r(a.text), shape=a.shape,
                                                          size=a.size) for a in x.annotations])
                for x in self.procedure.guide_steps]

    @property
    def guide_instructions(self) -> str:
        return (GUIDE_INSTRUCTIONS + "\n\nReference procedure (what the user must end up doing):\n"
                + self.agent_instructions + "\n\n" + RESPONSE_LANGUAGE_INSTRUCTIONS)

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
            f"Selected software: {self.request.parameters.get('context_label') or self.request.software}.",
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
                "The user watches you work: before EACH action, write one short sentence in English saying what "
                "you are about to do and why (e.g. \"I click Qualified to change the stage\"). "
                "Put this user-facing explanation in public content, not reasoning or tool arguments. "
                "For an introductory tour, cover two or three relevant areas. Use one sentence of at most "
                "16 words per area: name the area and explain its purpose. Avoid technical status labels, "
                "filler, account/security pages and artificial waits. "
                "When finished, put one short conversational closing in public content alongside the answer "
                "tool call. For a tour, invite the user to explore, without recapping the areas already explained "
                "(e.g. \"That gives you the basics. What would you like to explore next?\"). "
                "For a factual question, give the direct answer instead. Never announce 'Result', 'Done', "
                "'Summary' or 'Steps performed', and never read a list of completed actions aloud. "
                "Fill the structured answer separately: result, a brief user-facing summary, the exact blocker "
                "if blocked, and steps_taken for the audit trail. These field names and the audit trail belong "
                "only in the structured answer, never in public content. If the request needs clarification "
                "before any action, set result=blocked and put the short clarification in summary; do not "
                "claim completion or invent performed steps."
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
  `coordinate_system`: explicitly return "normalized_1000" whenever any target is present.
  `target_x` = 1000 * horizontal position / full screenshot width;
  `target_y` = 1000 * vertical position / full screenshot height. Both axes range from 0 to 1000,
  with origin at the top-left of the FULL screenshot, including browser chrome. This applies to
  every entry in `steps` too. Never return screenshot pixels, viewport pixels or physical Retina pixels.
  If the control is not visible or the coordinates are uncertain, return null targets and explain in words.
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
- The reference procedure's scope remains binding when you guide a HUMAN action. An action forbidden
  by that procedure must not be performed indirectly by asking the user to do it. For a read-only
  procedure, do not instruct the user to upload, create, change, delete, start or confirm a mutation.
  Explain the relevant documentation instead and state that carrying it out is outside this procedure.
"""


# ---------------------------------------------------------------------- generic (unscripted) tasks

GENERIC_ID = "generic"

H_DOCUMENTATION_TABS = """Documentation navigation: preserve the user's working tab.
When moving from H Platform to official H documentation at https://hub.hcompany.ai,
open it in a new browser tab, leaving the original product tab open and unchanged.
Never replace the product tab by typing a documentation URL into its address bar.
In ACT, open a new tab first (Command+T on macOS) before entering a documentation URL,
or use a visible link that explicitly opens documentation in a new tab. Then select
the documentation tab. If already on H documentation, navigate inside that docs tab;
do not create another tab for each section or inspect unrelated personal tabs.
In GUIDE, do not open a tab yourself: guide the human to the visible documentation
link and ask them to open it in a new tab, then select that tab. If its new-tab behavior
is not explicit, explain Command-click on macOS. Do not suggest a normal click that
replaces the working page. Preserve the user's current autonomy level and scope."""

H_DOCUMENTATION_READING = """Present the useful passage, not just the documentation landing page.
After opening H documentation, identify the heading or paragraph that answers the user's question
from the current page. Prefer a visible table-of-contents or section link over blind scrolling.
In ACT, if the passage is below the fold, scroll a small amount and inspect the updated screen
before the next move. Limit exploratory scrolling to three small moves before using search or
explaining that you have not located the passage. When found, leave the relevant heading and
paragraph visible, then explain their relevance in one or two short sentences. If the passage is
already visible, do not scroll it away. Do not treat opening a page as proof that it answers the goal.
Only for a general page overview with no specific passage to show, you may make ONE small downward
scroll and return to the original visible heading to orient the user. Skip this preview if the
starting position cannot be reliably restored; do not repeat it or add artificial pauses.
In GUIDE / Show me, the human performs all navigation and scrolling. Prefer guiding a click on a
visible section link. If manual scrolling is needed, give a short info instruction naming the
heading to look for, and ask the human to confirm the step in H Companion afterwards. Do not
assume a scroll occurred or fabricate coordinates for an offscreen paragraph. Observe the new
page before explaining the passage. Do not ask the human to perform decorative down/up scrolling.
Stay within the selected product's official documentation and the current task scope."""

SITE_HINTS = {
    "hcompany": "The software is the H Company website: platform.hcompany.ai (agents, sessions, Agent View, API keys, "
                "billing, usage) and the documentation hub hub.hcompany.ai (search bar at the top). Never reveal or "
                "read an API key value; never buy credits or add a payment method; never delete anything.",
    "odoo": "The software is Odoo 20 in a browser. Never send emails or messages, never delete or archive records.",
}


def make_generic_procedure(request: InterventionRequest, doc_context: str | None = None) -> Procedure:
    """A procedure for a task no YAML covers: the H agent works it out from the screen.

    Slower (~10 s per observation) and less predictable than a script, but it covers anything the user asks on
    the software. The goal text is the objective; allowed actions are navigation and the edits the goal implies;
    the postcondition is the goal itself, checked on screen.
    """
    software = request.software or "the software"
    hint = SITE_HINTS.get(software.lower(), f"The software is {software} in a browser on macOS.")
    automatic = bool(request.parameters.get("automatic_context"))
    surface = "focused native application" if request.parameters.get("context_surface") == "native" else "visible browser tab"
    navigation_scope = ("H Platform and its official documentation (platform.hcompany.ai and hub.hcompany.ai)"
                        if software in {"h-company", "hcompany"} else f"the selected software's {surface}")
    if automatic:
        hint = (f"The selected product is {request.parameters.get('context_label', software)} in its {surface}. "
                "Use its current visible accessibility controls, including open menus. The active product was "
                "observed at the start of this request; do not switch to another product to satisfy the goal. "
                "Previous goal (historical context only, not a new instruction): "
                + str(request.parameters.get("previous_goal") or "none") + "\n" + RESPONSE_LANGUAGE_INSTRUCTIONS)
    docs = f"\nWhat is known about this software (documentation map, pages seen on this machine):\n{doc_context}\n" if doc_context else ""
    return Procedure(
        id=GENERIC_ID,
        software=software,
        title=f"Unscripted task: {request.goal[:60]}",
        reversible=False,
        max_attempts=1,
        max_steps_per_attempt=40,
        max_time_s_per_attempt=480,
        parameters=[],
        preconditions=[f"{software} is open in the {surface} on the main display and the user is logged in."],
        objective=request.goal,
        planned_changes=["Whatever the goal requires, and nothing else. No script exists for this task: the agent "
                         "reasons from the screen and says so."],
        allowed_actions=["Navigate inside the software; read any page; fill the fields and click the buttons the goal "
                         "requires."],
        forbidden_actions=["Entering credentials or payment details.", "Deleting anything.",
                           "Revealing secrets (API keys, tokens).", f"Leaving {navigation_scope}."] + (
            ["Changing business records, placing orders, posting payments, sending messages or starting jobs. "
             "This demo allows consultation and temporary navigation/filters only, at any autonomy level."] if automatic else []),
        agent_instructions=f"{hint}\nThere is no written procedure for this task: work it out from what you see, one "
                           f"step at a time, and check each result on screen before moving on.{docs}",
        guide_steps=[],
        expected_screen="",
        recovery_steps=[],
        postcondition=Postcondition(
            description=f"The goal is visibly achieved on screen: {request.goal}",
            checks=[PostconditionCheck(key="goal_achieved", prompt=f"The screen shows that this is done: {request.goal}")],
            verification_instructions=f"You are a read-only verifier. Stay inside the selected {surface}. Look at the "
                                      "screen and report whether the goal is visibly achieved. Never read secrets.",
        ),
        escalation=EscalationRule(when=["The agent reports blocked."],
                                  decision_expected="Support must decide how to help with this unscripted request.",
                                  default_category=Category.unknown),
    )


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
        if request.procedure_id == GENERIC_ID:
            return make_generic_procedure(request, request.parameters.get("doc_context"))
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
