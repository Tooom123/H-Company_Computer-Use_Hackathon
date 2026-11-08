"""Voice entry point: push-to-talk -> Gladia transcription -> intent (procedure + parameters) -> request.

Hold the push-to-talk key, say what you want, release. The audio is transcribed by Gladia
(pre-recorded API, solaria-3), then Holo (H Models API, same key as the agent) maps the sentence onto
one of the known procedures and fills its parameters. The user still approves the plan before anything runs.
"""

from __future__ import annotations

import json
import os
import queue
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

import httpx
import numpy as np
from pydantic import BaseModel, Field

from .contract import InterventionRequest, Mode
from .procedures import Procedure, ProcedureRegistry

SAMPLE_RATE = 16_000
H_MODELS_URL = os.environ.get("HAI_MODELS_BASE_URL", "https://api.hcompany.ai/v1")


# --------------------------------------------------------------------------- recording


class Recorder:
    """Captures microphone audio between `start()` and `stop()`; returns a 16 kHz mono WAV path."""

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        import sounddevice as sd

        self._sd = sd
        self.sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream = None

    def start(self) -> None:
        self._chunks = []

        def cb(indata, frames, time_info, status):  # noqa: ARG001
            self._chunks.append(indata.copy())

        self._stream = self._sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="int16", callback=cb)
        self._stream.start()

    def stop(self) -> str | None:
        if self._stream is None:
            return None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._chunks:
            return None
        audio = np.concatenate(self._chunks)
        if len(audio) < self.sample_rate * 0.4:  # under 0.4 s: an accidental tap, not a sentence
            return None
        path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(audio.tobytes())
        return path


# --------------------------------------------------------------------------- transcription


class Transcriber:
    """Gladia pre-recorded transcription."""

    def __init__(self, api_key: str | None = None, language: str | None = None) -> None:
        from gladiaio_sdk import GladiaClient

        self._client = GladiaClient(api_key=api_key or os.environ["GLADIA_API_KEY"]).prerecorded()
        self.language = language or os.environ.get("HCS_VOICE_LANGUAGE", "fr")

    def transcribe(self, wav_path: str, vocabulary: list[str] | None = None) -> str:
        options: dict = {"model": "solaria-3", "language_config": {"languages": [self.language]}}
        if vocabulary:
            options["custom_vocabulary"] = True
            # Keep the bias gentle: at high intensity Gladia replaces ordinary words with vocabulary terms
            # ("mettre une note" became "opportunité CRM CRM").
            options["custom_vocabulary_config"] = {"vocabulary": [_vocab_entry(v) for v in vocabulary[:50]],
                                                   "default_intensity": 0.3}
        result = self._client.transcribe(wav_path, options)
        return _full_transcript(result)


# How French speakers actually say the demo names; Gladia maps these pronunciations back to the spelling.
_PRONUNCIATIONS = {
    "Acme Demo": ["acmé démo", "akmé démo"],
    "Acme Corp": ["acmé corp", "akmé corp"],
}


def _vocab_entry(word: str) -> dict:
    entry: dict = {"value": word, "intensity": 0.3}
    if word in _PRONUNCIATIONS:
        entry["pronunciations"] = _PRONUNCIATIONS[word]
        entry["intensity"] = 0.5
    return entry


def _full_transcript(result) -> str:
    for path in (("result", "transcription", "full_transcript"),):
        node = result
        for key in path:
            node = getattr(node, key, None) if not isinstance(node, dict) else node.get(key)
            if node is None:
                break
        if isinstance(node, str):
            return node.strip()
    return str(result)


# --------------------------------------------------------------------------- intent


class Intent(BaseModel):
    procedure_id: str | None = Field(description="One of the known procedure ids, or null if none fits.")
    question: str | None = Field(default=None, description="One short English question to ask the user when the "
                                                           "task or a required value is unclear; null otherwise.")
    point_at: str | None = Field(default=None, description="When the user asks where something is on the current "
                                                           "screen, an English description of that element; else null.")
    task: str | None = Field(default=None, description="When the user clearly asks for a task that no known procedure "
                                                       "covers, that task as one imperative English sentence; else null.")
    software: str | None = Field(default=None, description="Software the request is about: 'odoo', 'hcompany' or null.")
    mode: str | None = Field(default="act", description="'guide' if the user wants to be shown/explained how, else 'act'.")
    parameters: dict[str, str | int | float | None] | None = Field(default_factory=dict)
    role: str | None = None
    goal: str | None = Field(default="", description="The user's request, cleaned up, in English.")
    missing: list[str] | None = Field(default_factory=list, description="Required parameters not said by the user.")

    def model_post_init(self, __context) -> None:
        self.goal = self.goal or ""
        self.question = self.question or None
        self.point_at = (self.point_at or None) and str(self.point_at)
        self.task = (self.task or None) and str(self.task)
        self.software = (self.software or None) and str(self.software).lower()
        self.role = self.role or None
        self.mode = self.mode if self.mode in ("act", "guide") else "act"
        self.parameters = {k: str(v) for k, v in (self.parameters or {}).items() if v not in (None, "")}
        self.missing = list(self.missing or [])


def _intent_prompt(transcript: str, procedures: list[Procedure], history: list[str] | None = None) -> str:
    cat = []
    for p in procedures:
        params = ", ".join(f"{x.name}{'' if x.required else '?'} ({x.description})" for x in p.parameters)
        cat.append(f"- id={p.id} | software={p.software} | {p.title} | parameters: {params or 'none'}")
    convo = ""
    if history:
        convo = ("Earlier turns of this conversation, oldest first (assistant lines start with 'Assistant:'):\n"
                 + "\n".join(history[-8:]) + "\n\n"
                 "The new sentence may answer the assistant's question, correct a value ('actually 15000'), or "
                 "change the task. Merge it with the earlier turns: keep every value still valid, replace what the "
                 "user corrects.\n\n")
    return (
        "You are the ears of a support assistant: route a spoken request to a procedure, or ask what is unclear.\n"
        f"Today is {date.today().isoformat()}.\n"
        "Known procedures:\n" + "\n".join(cat) + "\n\n" + convo +
        f"User just said (transcribed speech, may contain errors): \"{transcript}\"\n\n"
        "Return ONLY a JSON object with keys: procedure_id (string or null), mode ('act' if the user wants it done "
        "for them, 'guide' if they want to learn / be shown / be explained how), parameters (object of strings; dates "
        "as YYYY-MM-DD, resolve relative dates like 'next Friday'; NEVER invent a value the user did not say), "
        "role (string or null), goal (one clean sentence in English, whatever language the user spoke), "
        "task (string or null: when the user asks to do or be shown something concrete on the software but NO known "
        "procedure fits, restate it as one imperative English sentence, set procedure_id null and question null; "
        "prefer a task over a question whenever the request names an action, even if details are missing — the "
        "agent will work them out on screen), "
        "software ('odoo', 'hcompany' when the request concerns the H Company platform, documentation, agents, "
        "sessions, API keys, credits; else null), "
        "point_at (string or null: when the user asks WHERE something is on the screen in front of them — 'where is the "
        "login button?', 'which field is the amount?' — give an English visual description of that element, e.g. 'the "
        "Log in button', and set procedure_id null and question null), "
        "missing (required parameters the user did not give), question (string or null: when the request could "
        "match several procedures, or a required value is missing, or the sentence is too garbled, ONE short "
        "friendly English question that gets exactly the missing piece; null when everything is clear). No prose."
    )


class IntentRouter:
    """Maps a transcript to a procedure and parameters with Holo through the H Models API."""

    def __init__(self, registry: ProcedureRegistry, api_key: str | None = None, model: str | None = None) -> None:
        from hai_agents.client import default_api_key

        self.registry = registry
        self.api_key = api_key or default_api_key()
        self.model = model or os.environ.get("HCS_MODEL", "holo4-35b-a3b")

    def route(self, transcript: str, history: list[str] | None = None) -> Intent:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": _intent_prompt(transcript, self.registry.all(), history)}],
            "max_tokens": 600,
            "temperature": 0,
            # Routing is a lookup, not a puzzle: skipping the thinking phase gives the JSON in ~1 s instead of ~10 s.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        r = httpx.post(f"{H_MODELS_URL}/chat/completions", json=body, timeout=60,
                       headers={"Authorization": f"Bearer {self.api_key}"})
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        # Holo may spend the budget in `reasoning` and leave `content` empty; the JSON can be in either.
        content = msg.get("content") or msg.get("reasoning") or ""
        intent = Intent.model_validate(_extract_json(content))
        if intent.procedure_id and intent.procedure_id not in {p.id for p in self.registry.all()}:
            intent.procedure_id = None
        if intent.procedure_id:
            proc = self.registry.get(intent.procedure_id)
            intent.missing = [p.name for p in proc.parameters if p.required and p.name not in intent.parameters
                              and p.default is None]
            if intent.missing and not intent.question:
                descs = [next(p.description for p in proc.parameters if p.name == n) for n in intent.missing]
                intent.question = "Which " + " and which ".join(d.split(",")[0].lower() for d in descs) + "?"
        elif not intent.question and not intent.point_at and not intent.task:
            intent.question = "I did not catch what you want to do. Which task should I help with?"
        return intent


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON in model output: {text[:200]}")
    return json.loads(text[start:end + 1])


def generic_request(intent: Intent, doc_context: str | None = None) -> InterventionRequest:
    """An unscripted task: the general H agent will work it out from the screen."""
    from .procedures import GENERIC_ID

    params = {"doc_context": doc_context} if doc_context else {}
    return InterventionRequest(
        software=intent.software or "hcompany", role=intent.role, goal=intent.task or intent.goal,
        procedure_id=GENERIC_ID, parameters=params,
        mode=Mode(intent.mode) if intent.mode in ("act", "guide") else Mode.guide,
    )


def intent_to_request(intent: Intent, software: str | None = None) -> InterventionRequest:
    if not intent.procedure_id:
        raise ValueError("no matching procedure")
    return InterventionRequest(
        software=software or intent.procedure_id.split("_")[0],
        role=intent.role,
        goal=intent.goal,
        procedure_id=intent.procedure_id,
        parameters=intent.parameters,
        mode=Mode(intent.mode) if intent.mode in ("act", "guide") else Mode.act,
    )


# --------------------------------------------------------------------------- push-to-talk


@dataclass
class PushToTalk:
    """Hold the hotkey to record, release to transcribe. Uses the process-wide InputHub (single event tap)."""

    key_name: str = field(default_factory=lambda: os.environ.get("HCS_PTT_KEY", "cmd+h"))
    on_state: Callable[[str], None] = lambda s: None
    transcripts: "queue.Queue[str]" = field(default_factory=queue.Queue)
    vocabulary: list[str] = field(default_factory=list)
    paused: bool = False

    def __post_init__(self) -> None:
        from .inputs import InputHub

        self._hub = InputHub.get()
        self._hub.set_combo(self.key_name)
        self._recorder = Recorder()
        self._transcriber = Transcriber()
        self._recording = False

    def _on_event(self, event: str, payload) -> None:
        if self.paused:
            return
        if event == "combo_down" or (event == "key_down" and self._hub.plain_key_matches(payload)):
            self._begin()
        elif event == "combo_up" or (event == "key_up" and self._hub.plain_key_matches(payload)):
            self._end()

    def _begin(self) -> None:
        if not self._recording:
            self._recording = True
            self.on_state("recording")
            self._recorder.start()

    def _end(self) -> None:
        if self._recording:
            self._recording = False
            path = self._recorder.stop()
            if not path:
                self.on_state("too_short")
                return
            self.on_state("transcribing")
            threading.Thread(target=self._transcribe, args=(path,), daemon=True).start()

    def _transcribe(self, path: str) -> None:
        try:
            text = self._transcriber.transcribe(path, self.vocabulary)
        except Exception as exc:  # noqa: BLE001
            self.on_state(f"error: {exc}")
            return
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        self.on_state("transcribed")
        self.transcripts.put(text)

    def set_key(self, key_name: str) -> None:
        """Change the hotkey live (desktop app). A recording in progress ends with the old key."""
        self.key_name = key_name
        self._hub.set_combo(key_name)

    def start(self) -> None:
        self._hub.subscribe(self._on_event)

    def stop(self) -> None:
        self._hub.unsubscribe(self._on_event)

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def wait_transcript(self, timeout: float | None = None) -> str | None:
        try:
            return self.transcripts.get(timeout=timeout)
        except queue.Empty:
            return None
