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


def allowed_page(url: str) -> bool:
    """Exact product/doc origins, with credential and billing pages excluded."""
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
        return not re.search(r"(?:^|/)(?:auth|login|signin|signup|vaults?|billing|api[-_]keys|credentials|password)(?:/|$)", path)
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
    if len(re.split(r"(?<=[.!?])\s+", text)) > 2:
        raise ValueError("Speech must contain at most two sentences.")
    return text


class CoachDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    speech: str = Field(max_length=MAX_SPEECH_CHARS, description="Plain English, 1–2 sentences, at most 32 words; empty only when done.")
    action: Literal["explain", "click", "type", "scroll", "key", "open_docs", "done"]
    target: int | None = Field(default=None, ge=1, description="Exact visible control ID; null when not needed.")
    text: str | None = Field(default=None, max_length=500, description="Literal input text for type, otherwise null.")
    direction: Literal["up", "down"] | None = None
    key: Literal["enter", "escape", "tab"] | None = None
    url: str | None = Field(default=None, max_length=2048)

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
            if not self.text or re.search(r"[\x00-\x1f\x7f]", self.text):
                raise ValueError("Typing requires literal single-line text.")
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
        return self


_UNSAFE_CONTROL = re.compile(
    r"\b(?:delete|remove|revoke|purchase|pay|subscribe|upgrade|billing|vaults?|password|credentials|payment)\b|"
    r"\b(?:api\s*keys?|generate\s+(?:a\s+)?key|create\s+(?:an?\s+)?(?:api\s+)?key)\b|"
    r"^(?:run|start|launch)(?:\s+(?:agent|session|job|task))?(?:\s|$)", re.I)


def _observation(raw: dict) -> dict:
    if not isinstance(raw, dict) or not allowed_page(raw.get("url", "")):
        raise CoachProtocolError("Open H Platform or its documentation first.")
    controls, seen = [], set()
    source = raw.get("controls", [])
    if not isinstance(source, list):
        raise CoachProtocolError("Invalid controls observation.")
    for control in source[:MAX_CONTROLS]:
        if not isinstance(control, dict):
            raise CoachProtocolError("Invalid control.")
        ident, box = control.get("id"), control.get("box")
        if type(ident) is not int or ident < 1 or ident in seen:
            raise CoachProtocolError("Controls need unique positive IDs.")
        if (not isinstance(box, (list, tuple)) or len(box) != 4
                or not all(type(v) in (int, float) and math.isfinite(v) for v in box)
                or box[0] < 0 or box[1] < 0 or box[2] <= 0 or box[3] <= 0):
            raise CoachProtocolError("Invalid visible control bounds.")
        seen.add(ident)
        controls.append({"id": ident, "role": str(control.get("role", ""))[:60],
                         "label": str(control.get("label", ""))[:180], "box": list(box),
                         "enabled": control.get("enabled") if type(control.get("enabled")) is bool else None})
    excerpts = raw.get("text", [])
    if isinstance(excerpts, str):
        excerpts = [excerpts]
    if not isinstance(excerpts, list):
        raise CoachProtocolError("Invalid text observation.")
    text, remaining = [], 7000
    for item in excerpts:
        if not isinstance(item, str) or not remaining:
            continue
        item = item[:remaining]
        text.append(item)
        remaining -= len(item)
    return {"url": raw["url"], "title": str(raw.get("title", ""))[:250], "controls": controls, "text": text}


def _validate_target(decision: CoachDecision, observation: dict) -> None:
    if decision.target is None:
        return
    control = next((c for c in observation["controls"] if c["id"] == decision.target), None)
    if control is None:
        raise CoachProtocolError("Holo selected a control that is not in this observation.")
    if decision.action not in {"click", "type"}:
        return
    if control.get("enabled") is False:
        raise CoachProtocolError("The selected control is disabled.")
    if (urlsplit(observation["url"]).hostname == "platform.hcompany.ai"
            and _UNSAFE_CONTROL.search(control["label"])):
        raise CoachProtocolError("This version only navigates and explains; that control is outside its scope.")
    if decision.action == "type":
        role = control["role"].casefold().removeprefix("ax")
        if role not in {"textfield", "searchfield", "textarea", "combobox", "textbox"}:
            raise CoachProtocolError("Typing target is not an observed text input.")


class CoachClient:
    """One bounded, text-only Holo4 call per current AX observation.

    ``last_raw`` contains only the provider's tool arguments (no reasoning),
    retained even when rejected. Runtime code must re-check target identity and
    current foreground page before executing. This client never performs actions.
    """

    def __init__(self, api_key: str, model: str = "holo4-35b-a3b", transport=None):
        if not api_key:
            raise CoachProtocolError("An H API key is required.")
        try:
            system = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
            product = PRODUCT_KNOWLEDGE_PATH.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CoachProtocolError("The coach prompt or H product briefing is missing.") from exc
        if not system or not product:
            raise CoachProtocolError("The coach prompt and product briefing must not be empty.")
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
            raise CoachProtocolError("A question and an explicit coach mode are required.")
        observed = _observation(observation)
        # History is runtime-provided data. Keep only four compact turns; never
        # replay old screenshots, system prompts or provider reasoning.
        recent = []
        for item in (history or [])[-4:]:
            if isinstance(item, dict):
                recent.append({k: str(item[k])[:600] for k in ("speech", "action", "observation", "question") if k in item})
        schema = CoachDecision.model_json_schema()
        schema["required"] = list(schema["properties"])
        if mode == "guide":
            schema["properties"]["action"]["enum"].remove("open_docs")
            mode_rule = ('Current mode is GUIDE: point to observed controls for the person. '
                         'Do not open a documentation tab yourself. If no documentation link is visible, '
                         'explain that they can switch to "Do it, I watch" to have you open it.')
        else:
            mode_rule = "Current mode is ACT: choose one next action for the runtime to perform, or answer directly."
        body = {"model": self.model, "temperature": 0, "max_tokens": 320,
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "system", "content": self.system_prompt + "\n\n" + mode_rule},
                             {"role": "user", "content": json.dumps({
                                 "mode": mode, "question": question, "current_observation": observed,
                                 "recent_history": recent}, ensure_ascii=False)}],
                "tools": [{"type": "function", "function": {"name": "coach_step", "strict": True,
                           "description": "One short user-facing explanation and at most one next step.", "parameters": schema}}],
                "tool_choice": "required"}
        start = time.monotonic()
        try:
            response = self._http.post(MODELS_URL, json=body)
            if response.status_code != 200:
                raise CoachProtocolError(f"Holo returned HTTP {response.status_code}.")
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
            if mode == "guide" and decision.action == "open_docs":
                raise CoachProtocolError("Opening a new documentation tab requires act mode.")
            _validate_target(decision, observed)
            return decision
        except CoachProtocolError:
            raise
        except httpx.HTTPError as exc:
            raise CoachProtocolError(f"Holo request failed ({type(exc).__name__}).") from exc
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise CoachProtocolError("Holo returned an invalid coaching step.") from exc
        finally:
            self.last_latency_s = time.monotonic() - start
