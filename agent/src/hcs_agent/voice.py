"""Voice entry point: push-to-talk -> selected transcription -> intent -> request.

Hold the push-to-talk key, say what you want, release. The audio is transcribed by Gladia or Voxtral
(live streaming with a same-provider file fallback), then Holo (H Models API, same key as the agent) maps the sentence onto
one of the known procedures and fills its parameters. The user still approves the plan before anything runs.
"""

from __future__ import annotations

import json
import os
import queue
import re
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

# Automatic mode can start on any supported product. Keep this to proper names:
# biasing ordinary words previously caused substitutions in unrelated speech.
# These are recognition hints only; provider transcripts remain verbatim.
AUTO_PRODUCT_VOCABULARY = (
    "H Company", "H Platform", "Holo", "H Companion", "Devin", "Cognition",
    "Odoo", "SAP", "ComfyUI", "Comfy Cloud", "CapCut",
)


# --------------------------------------------------------------------------- recording


class Recorder:
    """Captures microphone audio between `start()` and `stop()`; returns a 16 kHz mono WAV path."""

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        import sounddevice as sd

        self._sd = sd
        self.sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream = None

    on_chunk: Callable[[bytes], None] | None = None  # live listener (streaming transcription)

    def start(self) -> None:
        self._chunks = []

        def cb(indata, frames, time_info, status):  # noqa: ARG001
            self._chunks.append(indata.copy())
            if self.on_chunk is not None:
                try:
                    self.on_chunk(indata.tobytes())
                except Exception:  # noqa: BLE001 - the live path is best effort; the WAV fallback remains
                    pass

        self._stream = self._sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="int16", callback=cb,
                                             blocksize=int(self.sample_rate * 0.1))
        try:
            self._stream.start()
        except Exception:
            self.cancel()
            raise

    def cancel(self) -> None:
        """Release the microphone without writing or transcribing unfinished audio."""
        stream, self._stream = self._stream, None
        try:
            if stream is not None:
                stream.close()
        finally:
            self._chunks = []

    def stop(self) -> str | None:
        if self._stream is None:
            return None
        stream, self._stream = self._stream, None
        try:
            stream.stop()
        finally:
            stream.close()
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


def _language_config(language: str) -> dict:
    """Allow explicit French/English code-switching without translating the transcript."""
    if language == "fr-en":
        return {"languages": ["fr", "en"], "code_switching": True}
    return {"languages": [language], "code_switching": False}


def transcription_backends():
    """Select one provider for both live and file fallback; never cross-send audio."""
    provider = os.environ.get("HCS_STT_PROVIDER", "gladia").strip().lower()
    if provider == "voxtral":
        from .voxtral import VoxtralLiveTranscriber, VoxtralTranscriber
        return provider, VoxtralTranscriber, VoxtralLiveTranscriber
    if provider == "gladia":
        return provider, Transcriber, LiveTranscriber
    raise ValueError("HCS_STT_PROVIDER must be gladia or voxtral")


class LiveTranscriber:
    """Gladia live transcription: audio streams to Gladia WHILE the user speaks, so the text is ready a few
    hundred milliseconds after the key is released instead of 3-4 s later (the Kosmo lesson).

    Lifecycle per utterance: `open()` (POST /v2/live, connect the WebSocket — done at key-down, in a thread),
    `feed(pcm16)` from the microphone callback, `finish()` at key-up (sends stop_recording, waits for the
    final transcript). Anything failing -> None, and the caller falls back to the pre-recorded path.
    """

    INIT_URL = "https://api.gladia.io/v2/live"

    def __init__(self, api_key: str | None = None, language: str | None = None, sample_rate: int = SAMPLE_RATE) -> None:
        self.api_key = api_key or os.environ.get("GLADIA_API_KEY", "")
        self.language = language or os.environ.get("HCS_VOICE_LANGUAGE", "fr")
        self.sample_rate = sample_rate
        self._ws = None
        self._queue: "queue.Queue[bytes | None]" = queue.Queue()
        self._finals: dict[str, str] = {}
        self._partial = ""
        self._full: str | None = None
        self._done = threading.Event()
        self._final_after_stop = threading.Event()  # an is_final transcript arrived after stop_recording
        self._stopped_at: float | None = None
        self._failed: str | None = None
        self._opened = threading.Event()
        self.on_partial: Callable[[str], None] | None = None

    # -- session ---------------------------------------------------------------------------------
    def open(self, vocabulary: list[str] | None = None) -> None:
        """Create the session and connect; runs in its own thread so key-down returns at once."""
        self._reset()
        threading.Thread(target=self._run, args=(vocabulary or [],), daemon=True, name="gladia-live").start()

    def _reset(self) -> None:
        self._ws = None
        self._queue = queue.Queue()
        self._finals, self._partial, self._full, self._failed = {}, "", None, None
        self._stopped_at = None
        self._done.clear()
        self._final_after_stop.clear()
        self._opened.clear()

    def _run(self, vocabulary: list[str]) -> None:
        import json

        import httpx
        from websockets.sync.client import connect

        try:
            body = {
                "encoding": "wav/pcm", "sample_rate": self.sample_rate, "bit_depth": 16, "channels": 1,
                "model": "solaria-1",
                "language_config": _language_config(self.language),
                "messages_config": {"receive_partial_transcripts": True, "receive_final_transcripts": True,
                                    "receive_post_processing_events": False, "receive_acknowledgments": False,
                                    "receive_lifecycle_events": False},
            }
            if vocabulary:  # the live API nests the vocabulary under realtime_processing
                body["realtime_processing"] = {
                    "custom_vocabulary": True,
                    "custom_vocabulary_config": {"vocabulary": [_vocab_entry(v) for v in vocabulary[:50]],
                                                 "default_intensity": 0.3},
                }
            r = httpx.post(self.INIT_URL, headers={"x-gladia-key": self.api_key}, json=body, timeout=8)
            r.raise_for_status()
            url = r.json()["url"]
            ws = connect(url, open_timeout=8, close_timeout=2, max_size=None)
        except Exception as exc:  # noqa: BLE001
            self._failed = f"live init: {exc}"
            self._opened.set()
            self._done.set()
            return
        self._ws = ws
        self._opened.set()

        def sender() -> None:
            try:
                while True:
                    chunk = self._queue.get()
                    if chunk is None:
                        ws.send(json.dumps({"type": "stop_recording"}))
                        return
                    ws.send(chunk)  # binary PCM16 frames
            except Exception as exc:  # noqa: BLE001
                self._failed = f"live send: {exc}"
                self._done.set()

        threading.Thread(target=sender, daemon=True, name="gladia-live-send").start()
        try:
            for raw in ws:
                msg = json.loads(raw)
                kind = msg.get("type")
                if kind == "transcript":
                    data = msg.get("data") or {}
                    text = ((data.get("utterance") or {}).get("text") or "").strip()
                    if data.get("is_final"):
                        self._finals[str(data.get("id"))] = text
                        self._partial = ""
                        if self._stopped_at is not None:
                            self._final_after_stop.set()
                    else:
                        self._partial = text
                    if self.on_partial:
                        self.on_partial(self.text_so_far())
                elif kind == "post_final_transcript":
                    full = (((msg.get("data") or {}).get("transcription") or {}).get("full_transcript") or "").strip()
                    if full:
                        self._full = full
                    self._done.set()
                    break
                elif kind == "error":
                    self._failed = f"live: {msg.get('data')}"
                    self._done.set()
                    break
        except Exception as exc:  # noqa: BLE001 - connection closed by Gladia after the final (code 1000) is normal
            if not self._finals and not self._full:
                self._failed = f"live recv: {exc}"
        finally:
            self._done.set()
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    # -- audio -----------------------------------------------------------------------------------
    def feed(self, pcm16: bytes) -> None:
        if self._failed is None:
            self._queue.put(pcm16)

    def text_so_far(self) -> str:
        return " ".join([*(t for t in self._finals.values() if t), self._partial]).strip()

    def finish(self, timeout: float = 2.5) -> str | None:
        """Key released: stop and return the text as soon as the last utterance is final (~0.1-0.5 s).
        Gladia's post-processing (full transcript) comes 1-2 s later and is not worth waiting for.
        None on failure (the caller uses the pre-recorded path)."""
        if not self._opened.wait(timeout=2.0) or self._failed:
            return None
        self._stopped_at = time.time()
        self._queue.put(None)
        # Either a final arrives after the stop, or the session ends (post_final / close), or we time out.
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._final_after_stop.wait(timeout=0.05) or self._done.is_set():
                break
        if self._failed and not self._finals and not self._full:
            return None
        text = self._full or " ".join(t for t in self._finals.values() if t).strip() or self._partial.strip()
        self.cancel()  # we have what we need; let the socket close in the background
        return text or None

    def cancel(self) -> None:
        if self._stopped_at is None:
            self._stopped_at = time.time()
            self._queue.put(None)


class Transcriber:
    """Gladia pre-recorded transcription."""

    def __init__(self, api_key: str | None = None, language: str | None = None) -> None:
        from gladiaio_sdk import GladiaClient

        self._client = GladiaClient(api_key=api_key or os.environ["GLADIA_API_KEY"]).prerecorded()
        self.language = language or os.environ.get("HCS_VOICE_LANGUAGE", "fr")

    def transcribe(self, wav_path: str, vocabulary: list[str] | None = None) -> str:
        options: dict = {"model": "solaria-3", "language_config": _language_config(self.language)}
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
    ask: str | None = Field(default=None, description="When the user asks an information question (how many, what is, "
                                                      "can I, how does it work) that the documentation can answer, the "
                                                      "question in English; else null.")
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
        self.ask = (self.ask or None) and str(self.ask)
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
    site = ""
    try:
        from .sitemap import platform_summary

        known = "\n".join(f"{sw}:\n{platform_summary(sw, max_pages=6, max_controls=8)}" for sw in ("hcompany", "odoo")
                           if platform_summary(sw, max_pages=6, max_controls=8))
        if known:
            site = "Pages of the software seen on this machine (path: controls), to recognise what the user talks about:\n" + known + "\n\n"
    except Exception:  # noqa: BLE001
        site = ""
    return (
        "You are the ears of a support assistant: route a spoken request to a procedure, or ask what is unclear.\n"
        f"Today is {date.today().isoformat()}.\n"
        "Known procedures:\n" + "\n".join(cat) + "\n\n" + site + convo +
        f"User just said (transcribed speech, may contain errors): \"{transcript}\"\n\n"
        "Choose a procedure ONLY if completing it accomplishes what the user asked (creating an agent is not "
        "running a session; reviewing a session is not sharing it; redeeming a promo code is not checking credit "
        "usage; logging a note is not scheduling an activity); otherwise use task.\n"
        "Never answer with a question when the sentence is a clear information question (price, limits, what is, "
        "can I): put it in ask and let the documentation answer. 'Where is the X button / menu / field' is point_at, "
        "even if X is not visible right now. Environments differ: the cloud-session procedure is only for the cloud "
        "browser; 'my own Chrome', 'my Mac', 'my desktop' are other environments -> task or ask, never that procedure.\n"
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
        "ask (string or null: ONLY a pure information question with no action to show — 'how many sessions can I run "
        "at once?', 'what is a skill?', 'does the free plan include X?' — restated in English. 'How do I create / "
        "configure / run / share X' and 'show me how to X' are NEVER ask: they are a task (or a procedure), because the "
        "user wants to be shown the steps on screen), "
        "point_at (string or null: ONLY when the user asks WHERE a specific control is on the screen in front of them — "
        "'where is the login button?', 'which field is the amount?' — give an English visual description of that "
        "element, e.g. 'the Log in button'; never for 'how can I see / find out' questions, those are ask or task), "
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
        if _is_where_question(transcript):
            # "il est où le bouton X" / "which field is the amount": point at it (or navigate to it if not visible);
            # a where-question is never a procedure to run nor a definition to read
            intent.point_at = intent.point_at or _where_target(transcript, intent)
            intent.procedure_id, intent.task, intent.ask, intent.question = None, None, None, None
        if _is_information_question(transcript) and (not _names_an_action(transcript) or _CAPABILITY.search(transcript)) \
                and not intent.point_at:
            # A fact / capability / price / why question is answered from the documentation, never turned into a
            # task or a procedure ("can I run an agent on my own Chrome?", "how much does a session cost?").
            intent.ask = intent.ask or (intent.goal or transcript).strip()
            intent.task, intent.procedure_id, intent.question = None, None, None
        if intent.ask and not intent.procedure_id and _names_an_action(transcript) \
                and not _is_information_question(transcript):
            # "how do I create a skill" is a task to show on screen, not a definition to read out
            goal = (intent.goal or "").strip().rstrip("?.")
            intent.task = intent.task or (goal if goal and _names_an_action(goal) else f"Show how to: {transcript.strip().rstrip('?. ')}")
            intent.ask = None
        if intent.procedure_id and intent.procedure_id not in {p.id for p in self.registry.all()}:
            intent.procedure_id = None
        if intent.procedure_id:
            proc = self.registry.get(intent.procedure_id)
            intent.missing = [p.name for p in proc.parameters if p.required and p.name not in intent.parameters
                              and p.default is None]
            if intent.missing and not intent.question:
                descs = [next(p.description for p in proc.parameters if p.name == n) for n in intent.missing]
                intent.question = "Which " + " and which ".join(d.split(",")[0].lower() for d in descs) + "?"
        elif not intent.question and not intent.point_at and not intent.task and not intent.ask:
            intent.question = "I did not catch what you want to do. Which task should I help with?"
        return intent


_ACTION_WORDS = re.compile(
    r"\b(cr[ée]+r?|cr[ée]e|create|build|construire|faire|run|lancer|launch|configurer|configure|param[ée]trer|"
    r"ajouter|add|supprimer|delete|remove|partager|share|modifier|changer|change|edit|mettre|r[ée]gler|set ?up|"
    r"installer|install|d[ée]marrer|start|utiliser|use|activer|enable|d[ée]sactiver|disable|planifier|schedule|"
    r"envoyer|send|exporter|export|importer|import|connecter|connect|g[ée]n[ée]rer|generate|ouvrir|open|"
    r"montre|montrer|show|guide|explique[- ]moi comment|apprends)\w*", re.I)


_INFO_QUESTION = re.compile(
    r"^\W*(combien|how many|how much|c'est quoi|c est quoi|qu'est[- ]ce|what is|what's|what are|est[- ]ce que|does|do i|"
    r"is it|is there|are there|pourquoi|why|quelle? (?:est|sont)|which plan|quel plan|ai[- ]je|do we|can i|puis[- ]je|"
    r"est[- ]il possible)\b", re.I)


_WHERE_QUESTION = re.compile(
    r"^\W*(il est o[uù]|elle est o[uù]|ils sont o[uù]|o[uù] est|o[uù] se trouve|o[uù] sont|c'est o[uù]|where is|where are|"
    r"where's|where do i find|where can i find|c'est quoi (?:le|la|l')|c'est lequel|c'est laquelle|which (?:button|field|"
    r"menu|tab|link|icon|option)|quel (?:bouton|champ|menu|onglet|lien)|quelle (?:case|option|ic[oô]ne|liste))\b", re.I)
_CONTROL_WORDS = re.compile(r"\b(bouton|button|menu|champ|field|onglet|tab|lien|link|ic[oô]ne|icon|case|checkbox|"
                            r"option|liste|list|barre|bar|section|page|param[èe]tres?|settings?)\b", re.I)


def _is_where_question(text: str) -> bool:
    return bool(_WHERE_QUESTION.search(text or "")) and bool(_CONTROL_WORDS.search(text or ""))


def _where_target(transcript: str, intent) -> str:
    """An English description of the control asked about, from the model's restatement when it has one."""
    goal = (intent.goal or "").strip()
    m = re.search(r"\b(?:the|le|la|les|l')\s+(.+?)(?:\s+(?:is|are|located|situé|se trouve)\b|[?.]|$)", goal, re.I)
    if m and len(m.group(1)) > 3:
        return f"the {m.group(1).strip()}"
    return f"the control the user asks about: {transcript.strip().rstrip('?. ')}"


_CAPABILITY = re.compile(r"^\W*(est[- ]ce que je peux|puis[- ]je|can i|could i|is it possible|est[- ]il possible|"
                         r"combien co[uû]te|how much|pourquoi|why|est[- ]ce que (?:le|la|les|mon|ma|mes)\b)", re.I)


def _is_information_question(text: str) -> bool:
    """A question asking for a fact (how many / what is / does it…), not for steps to be shown."""
    return bool(_INFO_QUESTION.search(text or ""))


def _names_an_action(text: str) -> bool:
    """Does the sentence ask for something to be done or shown (create, run, configure, show me…)?"""
    return bool(_ACTION_WORDS.search(text or ""))


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
        self.stt_provider, transcriber, self._live_factory = transcription_backends()
        self._transcriber = transcriber()
        self._live: LiveTranscriber | None = None
        self.use_live = os.environ.get("HCS_STT_LIVE", "1").lower() not in {"0", "false", "no"}
        self._recording = False
        self._generation = 0
        self._generation_lock = threading.Lock()
        self._commands: "queue.Queue[str]" = queue.Queue()
        self._worker: threading.Thread | None = None

    def _on_event(self, event: str, payload) -> None:
        if self.paused:
            return
        if event == "combo_down" or (event == "key_down" and self._hub.plain_key_matches(payload)):
            self._commands.put("begin")
        elif event == "combo_up" or (event == "key_up" and self._hub.plain_key_matches(payload)):
            self._commands.put("end")

    def _run_commands(self) -> None:
        # Microphone permission/device startup can block. Never do it in the macOS event tap:
        # the release event must remain observable, even while start() is still opening the device.
        while True:
            command = self._commands.get()
            try:
                if command == "stop":
                    self._recording = False
                    self._recorder.cancel()
                    if self._live is not None:
                        self._live.cancel()
                        self._live = None
                    return
                if command == "begin":
                    self._begin()
                elif command == "end":
                    self._end()
            finally:
                self._commands.task_done()

    def _recording_error(self, exc: Exception) -> None:
        self._recording = False
        if self._live is not None:
            self._live.cancel()
            self._live = None
        try:
            self._recorder.cancel()
        except Exception:
            pass
        self.on_state(f"error: microphone {type(exc).__name__}: {str(exc)[:180]}")

    def _begin(self) -> None:
        if not self._recording:
            with self._generation_lock:
                self._generation += 1
                generation = self._generation
                while not self.transcripts.empty():
                    try:
                        self.transcripts.get_nowait()
                    except queue.Empty:
                        break
            try:
                self.on_state("starting")
                if self.use_live:
                    self._live = self._live_factory()
                    self._live.on_partial = lambda t: self._state_if_current(generation, f"partial: {t}")
                    self._live.open(self.vocabulary)
                    self._recorder.on_chunk = self._live.feed
                else:
                    self._recorder.on_chunk = None
                self._recorder.start()
            except Exception as exc:
                self._recording_error(exc)
                return
            self._recording = True
            self.on_state("recording")

    def _end(self) -> None:
        if self._recording:
            self._recording = False
            try:
                path = self._recorder.stop()
            except Exception as exc:
                self._recording_error(exc)
                return
            live, self._live = self._live, None
            if not path:
                if live:
                    live.cancel()
                self.on_state("too_short")
                return
            self.on_state("transcribing")
            threading.Thread(target=self._transcribe, args=(path, live, self._generation), daemon=True).start()

    def _state_if_current(self, generation: int, state: str) -> None:
        with self._generation_lock:
            if generation == self._generation:
                self.on_state(state)

    def _transcribe(self, path: str, live: "LiveTranscriber | None" = None, generation: int | None = None) -> None:
        generation = self._generation if generation is None else generation
        text = None
        try:
            t0 = time.time()
            if live is not None:
                text = live.finish()
                if text:
                    self._state_if_current(generation, f"transcribed live in {time.time() - t0:.1f}s")
            if not text:
                text = self._transcriber.transcribe(path, self.vocabulary)
                self._state_if_current(generation, f"transcribed (pre-recorded fallback) in {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            self._state_if_current(generation, f"error: {exc}")
            return
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        with self._generation_lock:
            if generation == self._generation:
                self.transcripts.put(text)

    def set_key(self, key_name: str) -> None:
        """Change the hotkey live (desktop app). A recording in progress ends with the old key."""
        self.key_name = key_name
        self._hub.set_combo(key_name)

    def start(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run_commands, name="push-to-talk-audio", daemon=True)
            self._worker.start()
        self._hub.subscribe(self._on_event)

    def stop(self) -> None:
        self._hub.unsubscribe(self._on_event)
        self._commands.put("stop")

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def wait_transcript(self, timeout: float | None = None) -> str | None:
        try:
            return self.transcripts.get(timeout=timeout)
        except queue.Empty:
            return None
