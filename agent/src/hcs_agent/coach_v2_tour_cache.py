"""Private cache of reviewed generic H Platform tours, rebound to each fresh AX page.

The caller supplies a fingerprint incorporating the model and both prompts, and
adds ``viewport`` (x, y, width, height) to the observation passed to get/put.
Only section labels, roles and concise narration are persisted; never AX IDs,
coordinates, page contents, screenshots or the user's question.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit
import uuid

from .coach_v2 import CoachDecision, allowed_page


VERSION = 1
TTL_SECONDS = 24 * 60 * 60
MAX_BYTES = 16 * 1024
SECTIONS = frozenset({"Agents", "Sessions", "Skills"})
ROLES = frozenset({"AXButton", "AXLink", "AXTab"})


def generic_tour_requested(question: str) -> bool:
    """Intentionally conservative: a targeted/mixed request must reach Holo."""
    if not isinstance(question, str) or len(question) > 300:
        return False
    text = re.sub(r"\s+", " ", question.casefold().replace("’", "'")).strip()
    text = re.sub(r"^(?:hey|hi|hello)(?:\s+(?:h[ -]?companion|companion))?\b[\s,!.]*", "", text)
    text = re.sub(r"^(?:i'm|i am) new (?:here|to (?:h platform|this platform))[\s,!.]*", "", text)
    text = text.strip(" ,.?!")
    prefix = r"(?:please )?(?:(?:can|could|would) you )?"
    platform = r"(?: (?:of|on) (?:h[ -]?company(?: platform)?|h platform|the platform|this platform))?"
    request = (r"(?:(?:give|show) me (?:a )?(?:(?:quick|welcome|short|brief) )+tour" + platform
               + r"|show me around(?: (?:h[ -]?company(?: platform)?|h platform|the platform|this platform))?"
               + r"|(?:a )?(?:(?:quick|welcome|short|brief) )+tour" + platform + r")")
    return re.fullmatch(prefix + request + r"(?:,? please)?", text) is not None


def _rect(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 4
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in value)
            or value[2] <= 0 or value[3] <= 0):
        return None
    return tuple(value)


def _sidebar(observation):
    """Find one complete aligned sidebar; body namesakes cannot supply cached IDs."""
    if not isinstance(observation, dict):
        return None
    url = observation.get("url", "")
    if not allowed_page(url) or urlsplit(url).hostname != "platform.hcompany.ai":
        return None
    viewport = _rect(observation.get("viewport"))
    controls = observation.get("controls")
    if viewport is None or not isinstance(controls, list) or len(controls) > 160:
        return None
    vx, vy, vw, vh = viewport
    seen, candidates = set(), []
    for control in controls:
        if not isinstance(control, dict):
            return None
        ident = control.get("id")
        if type(ident) is not int or ident < 1 or ident in seen:
            return None
        seen.add(ident)
        if (not isinstance(control.get("label"), str) or not isinstance(control.get("role"), str)
                or control.get("label") not in SECTIONS or control.get("role") not in ROLES
                or control.get("enabled") is False):
            continue
        box = _rect(control.get("box"))
        if box is None:
            continue
        x, y, width, height = box
        if (not 0 <= (x - vx) / vw <= .3 or width > vw * .33
                or not vx <= x + width / 2 <= vx + vw
                or not vy <= y + height / 2 <= vy + vh):
            continue
        candidates.append((control, box))
    rails = {}
    for _, anchor in candidates:
        grouped = {label: [] for label in SECTIONS}
        for control, box in candidates:
            if abs(box[0] - anchor[0]) <= vw * .02 and abs(box[2] - anchor[2]) <= vw * .03:
                grouped[control["label"]].append(control)
        if all(len(matches) == 1 for matches in grouped.values()):
            rail = {label: matches[0] for label, matches in grouped.items()}
            rails[tuple(sorted(c["id"] for c in rail.values()))] = rail
    return next(iter(rails.values())) if len(rails) == 1 else None


class TourCache:
    """Best-effort, mode-specific 24-hour cache; any uncertainty is a cache miss."""

    def __init__(self, path: Path, fingerprint: str):
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("A model-and-prompts fingerprint is required.")
        self.path = Path(path)
        self.fingerprint = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        self._lock = threading.RLock()

    def _read(self):
        if self.path.is_symlink() or self.path.parent.is_symlink():
            return None
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if info.st_mode & 0o077 or info.st_size > MAX_BYTES:
                    return None
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return None
            data = json.loads(raw)
            if (not isinstance(data, dict) or data.get("version") != VERSION
                    or data.get("fingerprint") != self.fingerprint or not isinstance(data.get("entries"), dict)):
                return None
            return data
        except (OSError, ValueError, TypeError):
            return None

    def get(self, question: str, observationdata: dict, mode: str) -> CoachDecision | None:
        if not isinstance(mode, str) or mode not in {"guide", "act"} or not generic_tour_requested(question):
            return None
        rail = _sidebar(observationdata)
        if rail is None:
            return None
        with self._lock:
            data = self._read()
        if data is None:
            return None
        try:
            entry = data["entries"][mode]
            saved_at = entry["saved_at"]
            age = time.time() - saved_at
            if type(saved_at) not in (int, float) or not math.isfinite(saved_at) or not 0 <= age < TTL_SECONDS:
                return None
            points = []
            for point in entry["points"]:
                control = rail[point["label"]]
                if point["role"] != control["role"]:
                    return None
                points.append({"target": control["id"], "speech": point["speech"]})
            return CoachDecision.model_validate({"action": "tour", "speech": entry["speech"], "points": points})
        except (KeyError, ValueError, TypeError):
            return None

    def put(self, question: str, decision: CoachDecision, observationdata: dict, mode: str) -> bool:
        if not isinstance(mode, str) or mode not in {"guide", "act"} or not generic_tour_requested(question):
            return False
        rail = _sidebar(observationdata)
        if rail is None:
            return False
        try:
            decision = CoachDecision.model_validate(decision.model_dump())
            if decision.action != "tour":
                return False
            controls = {control["id"]: control for control in rail.values()}
            points = [{"label": controls[p.target]["label"], "role": controls[p.target]["role"], "speech": p.speech}
                      for p in decision.points]
            entry = {"saved_at": time.time(), "speech": decision.speech, "points": points}
        except (AttributeError, KeyError, ValueError, TypeError):
            return False
        with self._lock:
            if self.path.is_symlink() or self.path.parent.is_symlink():
                return False
            data = self._read() or {"version": VERSION, "fingerprint": self.fingerprint, "entries": {}}
            data["entries"][mode] = entry
            temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
                if len(encoded) > MAX_BYTES:
                    return False
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(encoded)
                temporary.replace(self.path)
                return True
            except (OSError, ValueError, TypeError):
                return False
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
