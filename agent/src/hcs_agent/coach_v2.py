"""A single Holo4 decision from current H Platform evidence. No desktop execution.

This module intentionally does not import the legacy CLI, procedure registry,
runner, retrieval pipeline, or verifier. The runtime owns input, observations,
action execution and user feedback. ``done`` is a model decision, not a label.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import time
from datetime import datetime
from typing import Literal
from urllib.parse import unquote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


DATA = Path(__file__).parent / "data"
SYSTEM_PROMPT_PATH = DATA / "hcompany-coach-v2-system.md"
PRODUCT_KNOWLEDGE_PATH = DATA / "hcompany-coach-v2.md"
MODELS_URL = "https://api.hcompany.ai/v1/chat/completions"
MAX_WORDS = 32
MAX_SPEECH_CHARS = 220
MAX_CONTROLS = 160


class CoachProtocolError(ValueError):
    """The observation/response cannot safely become a coaching step."""

    def __init__(self, message: str, *, kind: str = "response", reason: str | None = None,
                 validation_errors: list[dict] | None = None):
        super().__init__(message)
        self.kind = kind
        self.reason = reason
        # Structured diagnostics deliberately omit model inputs and provider bodies.
        self.validation_errors = validation_errors or []


def allowed_page(url: str) -> bool:
    """Exact product/doc origins; account pages require the runtime's safe observer."""
    if not isinstance(url, str) or re.search(r"[\x00-\x20]", url):
        return False
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in {"platform.hcompany.ai", "hub.hcompany.ai"}
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            return False
        if parsed.hostname == "hub.hcompany.ai":
            return True
        path = unquote(parsed.path).casefold()
        return not re.search(r"(?:^|/)(?:auth|login|signin|signup|vaults?|credentials|password)(?:/|$)", path)
    except (TypeError, ValueError):
        return False


def allowed_docs_url(url: str) -> bool:
    return allowed_page(url) and urlsplit(url).hostname == "hub.hcompany.ai" and not re.search(r"[\x00-\x20]", url)


def concise_speech(value: str) -> str:
    """Enforce the display/voice contract without silently truncating meaning."""
    text = value.strip()
    if not text:
        return ""
    # Strip inline decoration before checking report prefixes; **Result:** is
    # just as unsuitable for the voice as Result:.
    if "```" in text:
        raise ValueError("Speech must be short plain prose, not code.")
    text = text.replace("**", "").replace("`", "")
    if (text.startswith(("{", "[")) or "```" in text or "|" in text
            or re.search(r"(?im)^\s*(?:#{1,6}\s|[-*]\s|\d+[.)]\s|(?:result|summary|steps performed|done)\s*:)", text)
            or re.search(r"\b\w+_(?:desktop|web)\s*\(", text)):
        raise ValueError("Speech must be short plain prose, not a report or code.")
    text = re.sub(r"\s+", " ", text)
    if len(text) > MAX_SPEECH_CHARS or len(text.split()) > MAX_WORDS:
        raise ValueError("Speech exceeds the compact coaching limit.")
    return text


class TourPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    speech: str = Field(min_length=1, max_length=MAX_SPEECH_CHARS,
                        description="One short explanation of this sidebar section, at most 32 words.")
    target: int = Field(ge=1, description="Exact observed sidebar ID: GUIDE highlights it; ACT opens Agents, Sessions or Skills.")

    @field_validator("speech")
    @classmethod
    def readable(cls, value: str) -> str:
        result = concise_speech(value)
        if not result:
            raise ValueError("A tour point needs an explanation.")
        return result


class CoachDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    speech: str = Field(max_length=MAX_SPEECH_CHARS, description="Plain English, 1–2 sentences, at most 32 words; empty only when done.")
    action: Literal["explain", "click", "type", "scroll", "key", "open_docs", "tour", "done"] = Field(
        description="Use type to focus an input AND enter text in one step. Click only activates a control and must have text=null. Tour only presents explicitly requested navigation sections.")
    target: int | None = Field(default=None, ge=1, description="Exact visible control ID; null when not needed.")
    text: str | None = Field(default=None, max_length=4000, description="Only action=type may carry text. Type focuses its target automatically before filling it; do not emit click with text. Markdown skill bodies may contain line breaks. Null for every other action.")
    direction: Literal["up", "down"] | None = None
    key: Literal["enter", "escape", "tab"] | None = None
    url: str | None = Field(default=None, max_length=2048)
    points: list[TourPoint] | None = Field(default=None, min_length=1, max_length=3,
                                         description="Only for a requested tour: one to three observed sidebar controls and brief explanations.")

    @model_validator(mode="before")
    @classmethod
    def normalize_unused_nulls(cls, value):
        """Accept provider null spellings only where the action cannot use a field.

        Do not convert literal search text, guess IDs/directions, discard a real
        extra action argument, or mutate ``last_raw`` retained by the client.
        """
        if not isinstance(value, dict):
            return value
        needed = {"target": {"click", "type"}, "text": {"type"},
                  "direction": {"scroll"}, "key": {"key"}, "url": {"open_docs"}, "points": {"tour"}}
        result = value.copy()
        if value.get("action") != "tour" and result.get("points") == []:
            result["points"] = None
        for field, actions in needed.items():
            item = result.get(field)
            if (value.get("action") not in actions and isinstance(item, str)
                    and item.strip().casefold() in {"", "none", "null"}):
                result[field] = None
        return result

    @field_validator("speech")
    @classmethod
    def readable(cls, value: str) -> str:
        return concise_speech(value)

    @model_validator(mode="after")
    def coherent_action(self):
        if not self.speech and self.action != "done":
            raise ValueError("A coaching step needs a short explanation.")
        if self.action in {"click", "type"} and self.target is None:
            raise ValueError("This action requires an observed target.")
        if self.action not in {"click", "type", "explain"} and self.target is not None:
            raise ValueError("This action must not carry a target.")
        if self.action == "type":
            if not self.text or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", self.text):
                raise ValueError("Typing requires literal text without control commands.")
        elif self.text is not None:
            raise ValueError("Only a typing action may include text.")
        if (self.action == "scroll") != (self.direction is not None):
            raise ValueError("Only a scroll action requires a direction.")
        if (self.action == "key") != (self.key is not None):
            raise ValueError("Only a key action requires a key.")
        if self.action == "open_docs":
            if not self.url or not allowed_docs_url(self.url):
                raise ValueError("Documentation must use the official H Hub origin.")
        elif self.url is not None:
            raise ValueError("Only open_docs may include a URL.")
        if (self.action == "tour") != (self.points is not None):
            raise ValueError("Only a tour requires one to three points.")
        if self.points and len({p.target for p in self.points}) != len(self.points):
            raise ValueError("A tour must highlight distinct controls.")
        return self


_UNSAFE_CONTROL = re.compile(
    r"\b(?:delete|remove|revoke|purchase|pay|subscribe|upgrade|vaults?|password|credentials|payment)\b|"
    r"^(?:run|start|launch)(?:\s+(?:agent|session|job|task))?(?:\s|$)", re.I)


def tour_requested(question: str) -> bool:
    """A tour is an explicit presentation request, never a guessed batch of clicks."""
    return bool(re.search(
        r"\b(?:give|show|take|walk|offer)\b.{0,70}\b(?:tour|around|overview)\b|"
        r"\b(?:montre|présente|presente|fais|faire|donne)\b.{0,70}\b(?:tour|visite|autour)\b|"
        r"^\s*(?:(?:a|quick|welcome|short|brief)\s+)*tour\b", question, re.I))


def sensitive_key_creation(decision: CoachDecision, observation: dict) -> bool:
    """The runtime must pause for the human before these credential-creation effects."""
    path = unquote(urlsplit(str(observation.get("url", ""))).path).casefold()
    key_page = bool(re.search(r"(?:^|/)(?:api[-_]?keys?|api[-_]?tokens?)(?:/|$)", path))
    if decision.action == "key":
        return key_page and decision.key == "enter"
    if decision.action != "click":
        return False
    controls = observation.get("controls", [])
    label = next((str(c.get("label", "")) for c in controls
                  if c.get("id") == decision.target), "")
    # H's list-page button opens the editor; it does not create a credential.
    # Exempt only that observed entry point, with positive list-page evidence
    # and no visible editor. Ambiguous or final Create/Generate buttons still
    # require confirmation, even when the list remains visible behind a dialog.
    normalized_label = " ".join(label.casefold().split())
    list_heading = any(c.get("role") == "AXHeading"
                       and " ".join(str(c.get("label", "")).casefold().split()) == "api keys"
                       for c in controls)
    form_visible = any(
        c.get("role") in {"AXDialog", "AXSheet"}
        or (c.get("role") in {"AXTextField", "AXTextArea", "AXComboBox", "AXPopUpButton"}
            and re.search(r"\b(?:name|expiry|expiration|expires?|duration)\b", str(c.get("label", "")), re.I))
        or (c.get("role") == "AXHeading"
            and re.search(r"\b(?:create|generate|add|new)\b.{0,35}\b(?:key|token)\b",
                          str(c.get("label", "")), re.I))
        or str(c.get("label", "")).strip().casefold() == "cancel"
        for c in controls)
    if (key_page and normalized_label in {"create an api key", "new api key"}
            and list_heading and not form_visible):
        return False
    explicit = re.search(r"\b(?:create|generate|add|new)\b.{0,35}\b(?:api\s*)?(?:key|token)\b", label, re.I)
    final = re.fullmatch(r"\s*(?:create|generate|add|save|confirm|submit)(?:\s+(?:key|token))?\s*", label, re.I)
    return bool(explicit or key_page and final)


def _observation(raw: dict) -> dict:
    if not isinstance(raw, dict) or not allowed_page(raw.get("url", "")):
        raise CoachProtocolError("Open H Platform or its documentation first.", kind="observation", reason="outside_h_page")
    controls, seen = [], set()
    source = raw.get("controls", [])
    if not isinstance(source, list):
        raise CoachProtocolError("Invalid controls observation.", kind="observation", reason="invalid_controls")
    for control in source[:MAX_CONTROLS]:
        if not isinstance(control, dict):
            raise CoachProtocolError("Invalid control.", kind="observation", reason="invalid_control")
        ident, box = control.get("id"), control.get("box")
        if type(ident) is not int or ident < 1 or ident in seen:
            raise CoachProtocolError("Controls need unique positive IDs.", kind="observation", reason="invalid_control_ids")
        if (not isinstance(box, (list, tuple)) or len(box) != 4
                or not all(type(v) in (int, float) and math.isfinite(v) for v in box)
                or box[0] < 0 or box[1] < 0 or box[2] <= 0 or box[3] <= 0):
            raise CoachProtocolError("Invalid visible control bounds.", kind="observation", reason="invalid_control_bounds")
        seen.add(ident)
        controls.append({"id": ident, "role": str(control.get("role", ""))[:60],
                         "label": str(control.get("label", ""))[:180], "box": list(box),
                         "enabled": control.get("enabled") if type(control.get("enabled")) is bool else None})
    excerpts = raw.get("text", [])
    if isinstance(excerpts, str):
        excerpts = [excerpts]
    if not isinstance(excerpts, list):
        raise CoachProtocolError("Invalid text observation.", kind="observation", reason="invalid_observation_text")
    text, remaining = [], 7000
    for item in excerpts:
        if not isinstance(item, str) or not remaining:
            continue
        item = item[:remaining]
        text.append(item)
        remaining -= len(item)
    result = {"url": raw["url"], "title": str(raw.get("title", ""))[:250], "controls": controls, "text": text}
    quota = raw.get("account_quota")
    if quota is not None:
        if (not isinstance(quota, dict) or quota.get("source") != "H sessions quota API"
                or not all(k in quota and (quota[k] is None or type(quota[k]) is int and quota[k] >= 0)
                           for k in ("limit", "active", "available"))):
            raise CoachProtocolError("Invalid account quota observation.", kind="observation", reason="invalid_account_quota")
        stamp = quota.get("observed_at")
        try:
            if not isinstance(stamp, str) or len(stamp) > 64:
                raise ValueError("Missing timestamp")
            datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CoachProtocolError("Invalid quota timestamp.", kind="observation", reason="invalid_account_quota") from exc
        result["account_quota"] = {k: quota[k] for k in ("limit", "active", "available", "source", "observed_at")}
        if quota.get("account") == "configured_api_connection":
            result["account_quota"]["account"] = "configured_api_connection"
            result["account_quota"]["browser_account_match"] = "unverified"
    return result


def _validate_target(decision: CoachDecision, observation: dict) -> None:
    if decision.action == "tour":
        for point in decision.points or []:
            target = next((c for c in observation["controls"] if c["id"] == point.target), None)
            if target is None:
                raise CoachProtocolError("A tour point is not in this observation.", reason="unknown_tour_target")
            if target["role"] not in {"AXButton", "AXLink", "AXTab", "AXMenuItem"}:
                raise CoachProtocolError("A tour point must be a visible navigation control.", reason="invalid_tour_target")
    if decision.target is None:
        return
    control = next((c for c in observation["controls"] if c["id"] == decision.target), None)
    if control is None:
        raise CoachProtocolError("Holo selected a control that is not in this observation.", reason="unknown_target")
    if decision.action not in {"click", "type"}:
        return
    if control.get("enabled") is False:
        raise CoachProtocolError("The selected control is disabled.", kind="policy", reason="disabled_target")
    if (urlsplit(observation["url"]).hostname == "platform.hcompany.ai"
            and _UNSAFE_CONTROL.search(control["label"])):
        raise CoachProtocolError("This version only navigates and explains; that control is outside its scope.", kind="policy", reason="restricted_control")
    if decision.action == "type":
        role = control["role"].casefold().removeprefix("ax")
        if role not in {"textfield", "searchfield", "textarea", "combobox", "textbox"}:
            raise CoachProtocolError("Typing target is not an observed text input.", reason="invalid_typing_target")


def _model_observation(observed: dict) -> dict:
    """Send semantic AX evidence; retain geometry locally for validated execution.

    Holo returns control IDs, never coordinates. All IDs, roles, labels, explicit
    enabled states and page text are preserved; this does not select or rank
    targets. The original observation still validates both input and output.
    """
    return {**observed, "controls": [
        {key: value for key, value in control.items()
         if key != "box" and not (key == "enabled" and value is None)}
        for control in observed["controls"]]}


def _compact_schema(value):
    """Drop generated annotations, retaining all validation and field guidance."""
    if isinstance(value, dict):
        return {key: _compact_schema(item) for key, item in value.items()
                if key not in {"title", "default"}}
    if isinstance(value, list):
        return [_compact_schema(item) for item in value]
    return value


class CoachClient:
    """One bounded, text-only Holo4 call per current AX observation.

    ``last_raw`` contains only the provider's tool arguments (no reasoning),
    retained even when rejected. Runtime code must re-check target identity and
    current foreground page before executing. This client never performs actions.
    """

    def __init__(self, api_key: str, model: str = "holo4-35b-a3b", transport=None):
        if not api_key:
            raise CoachProtocolError("An H API key is required.", kind="configuration", reason="missing_api_key")
        try:
            system = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
            product = PRODUCT_KNOWLEDGE_PATH.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CoachProtocolError("The coach prompt or H product briefing is missing.", kind="configuration", reason="missing_briefing") from exc
        if not system or not product:
            raise CoachProtocolError("The coach prompt and product briefing must not be empty.", kind="configuration", reason="empty_briefing")
        self.system_prompt = system + "\n\nH Platform product briefing (reference data):\n" + product
        self.model = model
        self.last_raw: dict | str | None = None
        self.last_usage: dict = {}
        self.last_latency_s: float = 0.0
        self._http = httpx.Client(timeout=25, headers={"Authorization": f"Bearer {api_key}"}, transport=transport)

    def close(self):
        self._http.close()

    def decide(self, question: str, observation: dict, mode: Literal["guide", "act"], history: list[dict] | None = None) -> CoachDecision:
        self.last_raw, self.last_usage, self.last_latency_s = None, {}, 0.0
        if not isinstance(question, str) or not question.strip() or mode not in {"guide", "act"}:
            raise CoachProtocolError("A question and an explicit coach mode are required.", kind="configuration", reason="invalid_request")
        observed = _observation(observation)
        # History is runtime-provided data. Keep only four compact turns; never
        # replay old screenshots, system prompts or provider reasoning.
        recent = []
        for item in (history or [])[-4:]:
            if isinstance(item, dict):
                recent.append({k: str(item[k])[:600] for k in ("speech", "action", "observation", "question") if k in item})
        schema = _compact_schema(CoachDecision.model_json_schema())
        schema["required"] = list(schema["properties"])
        requested_tour = tour_requested(question)
        if not requested_tour:
            schema["properties"]["action"]["enum"].remove("tour")
        if mode == "guide":
            schema["properties"]["action"]["enum"].remove("open_docs")
            mode_rule = ('Current mode is GUIDE: point to observed controls for the person. '
                         'Do not open a documentation tab yourself. If no documentation link is visible, '
                         'explain that they can switch to "Do it, I watch" to have you open it.')
        else:
            mode_rule = "Current mode is ACT: choose one next action for the runtime to perform, or answer directly."
        mode_rule += (' For a form field, action="type" focuses the target and enters its text in ONE step. '
                      'Do not click a field as a separate preparation step while including text: '
                      'action="click" always requires text=null. '
                      'Use action="tour" only when it is present in the allowed action enum. '
                      'All speech and tour-point speech must be English, even when the request, page or recent history is French. '
                      'GUIDE narration tells the user what to do; never promise that you will click or type.')
        # A structured tour has three short speeches; a skill body is payload,
        # never narration. Give these requested forms room without lengthening voice.
        drafting_skill = bool(re.search(r"\b(?:skill|compétence)\b", question, re.I)
                              and re.search(r"\b(?:create|write|draft|crée|créer|rédige)\b", question, re.I))
        budget = 1500 if drafting_skill else 700 if requested_tour else 320
        body = {"model": self.model, "temperature": 0, "max_tokens": budget,
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "system", "content": self.system_prompt + "\n\n" + mode_rule},
                             {"role": "user", "content": json.dumps({
                                 "mode": mode, "question": question, "current_observation": _model_observation(observed),
                                 "recent_history": recent, "response_language": "English",
                                 "response_instructions": (
                                     "Write every speech field in English, including tour points. Do not imitate the language of the transcript or earlier replies. "
                                     + ("You guide: for click/type actions, address the person in the imperative: 'Click …', 'Open …', 'Type …'. "
                                        "Never describe these actions using 'I', 'I'll', 'I will', or 'Let me'."
                                        if mode == "guide" else "You act: briefly explain your next requested action.")
                                     + (" The browser account has NOT been matched to Companion's API connection. "
                                        "Never describe account_quota as 'your current plan'. Attribute those figures to "
                                        "Companion's API connection, then show Billing & Subscription to check the browser account."
                                        if "account_quota" in observed else ""))
                             }, ensure_ascii=False, separators=(",", ":"))}],
                "tools": [{"type": "function", "function": {"name": "coach_step", "strict": True,
                           "description": "One short user-facing explanation and at most one next step.", "parameters": schema}}],
                "tool_choice": "required"}
        start = time.monotonic()
        try:
            response = self._http.post(MODELS_URL, json=body)
            if response.status_code != 200:
                raise CoachProtocolError(f"Holo returned HTTP {response.status_code}.", kind="provider", reason=f"http_{response.status_code}")
            payload = response.json()
            if not isinstance(payload, dict):
                raise CoachProtocolError("Invalid Holo response envelope.")
            self.last_usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            message = payload["choices"][0]["message"]
            if not isinstance(message, dict):
                raise CoachProtocolError("Invalid Holo message.")
            calls = message.get("tool_calls") or []
            if (not isinstance(calls, list) or len(calls) != 1
                    or not isinstance(calls[0], dict) or not isinstance(calls[0].get("function"), dict)
                    or calls[0]["function"].get("name") != "coach_step"):
                raise CoachProtocolError("Holo must return exactly one coach step.")
            raw = calls[0]["function"]["arguments"]
            self.last_raw = raw
            if not isinstance(raw, str):
                raise CoachProtocolError("Invalid tool arguments.")
            self.last_raw = json.loads(raw)
            decision = CoachDecision.model_validate(self.last_raw)
            if decision.action == "tour" and not tour_requested(question):
                raise CoachProtocolError("A tour must be explicitly requested.", kind="policy", reason="unrequested_tour")
            if mode == "guide" and decision.action == "open_docs":
                raise CoachProtocolError("Opening a new documentation tab requires act mode.", kind="policy", reason="guide_open_docs")
            _validate_target(decision, observed)
            return decision
        except CoachProtocolError:
            raise
        except httpx.HTTPError as exc:
            raise CoachProtocolError(f"Holo request failed ({type(exc).__name__}).", kind="provider", reason=type(exc).__name__) from exc
        except ValidationError as exc:
            details = [{"loc": list(item["loc"]), "type": item["type"], "message": item["msg"]}
                       for item in exc.errors(include_input=False, include_context=False, include_url=False)]
            raise CoachProtocolError("Holo returned an invalid coaching step.", reason="invalid_step",
                                     validation_errors=details) from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise CoachProtocolError("Holo returned an invalid coaching step.", reason="invalid_payload") from exc
        finally:
            self.last_latency_s = time.monotonic() - start
