"""Private, append-only observations for the isolated H Platform coach.

No runner, API client or automatic success judge is involved. The compact report is
readable by the existing desktop control API; human labels remain DesktopFeedback's
responsibility and never upgrade the model's completion claim into verification.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _State(str, Enum):
    running = "running"
    awaiting_user = "awaiting_user"
    completed = "completed"
    blocked = "blocked"
    stopped = "stopped"
    failed = "failed"

    @property
    def terminal(self) -> bool:
        return self not in {_State.running, _State.awaiting_user}


def _write_private(path: Path, value: dict[str, Any]) -> None:
    """Atomic replacement, with a new private inode rather than inherited permissions."""
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class CoachRun:
    """One request, immutable terminal outcome, and explicit feedback compatibility.

    ``record`` accepts JSON-compatible payloads. It does not infer labels, token
    costs or success from them. ``report`` is a plain dictionary, initially None.
    ``runs_dir`` means this particular session directory, as DesktopFeedback expects.
    """

    def __init__(self, root: Path, goal: str, mode: str):
        mode = getattr(mode, "value", mode)
        if mode not in {"guide", "act"}:
            raise ValueError("mode must be guide or act")
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal must be nonempty text")
        root = Path(root)
        if root.is_symlink():
            raise ValueError("the private run root must not be a symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        self.session_id = f"coach_v2_{uuid.uuid4().hex}"
        self.runs_dir = root / self.session_id
        self.runs_dir.mkdir(mode=0o700)
        self.runs_dir.chmod(0o700)
        self.request = SimpleNamespace(session_id=self.session_id, goal=goal, mode=mode,
                                       software="h-company", procedure_id="h_platform_coach_v2")
        self.backend = SimpleNamespace(simulated=False)
        self.state = _State.running
        self.report: dict[str, Any] | None = None
        self._lock = threading.RLock()
        self._sequence = 0
        self._started_at = _now()
        _write_private(self.runs_dir / "request.json", {
            **vars(self.request), "created_at": self._started_at, "simulated": False,
        })
        self.record("started", {"mode": mode})

    def record(self, kind: str, payload: Any) -> None:
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("event kind must be nonempty text")
        with self._lock:
            entry = {"session_id": self.session_id, "sequence": self._sequence + 1,
                     "timestamp": _now(), "type": kind, "state": self.state.value,
                     "simulated": False, "payload": payload}
            line = (json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            fd = os.open(self.runs_dir / "events.jsonl",
                         os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "ab") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(line)
            self._sequence += 1

    def set_waiting(self) -> None:
        self._set_active(_State.awaiting_user)

    def set_running(self) -> None:
        self._set_active(_State.running)

    def _set_active(self, state: _State) -> None:
        with self._lock:
            if self.state.terminal or self.state is state:
                return
            self.state = state
            self.record("state_changed", {"state": state.value})

    def finish(self, status: str, speech: str) -> dict[str, Any]:
        aliases = {"done": "completed", "interrupted": "stopped", "error": "failed"}
        state = _State(aliases.get(status, status))
        if not state.terminal:
            raise ValueError("finish requires a terminal status")
        if not isinstance(speech, str):
            raise ValueError("speech must be text")
        with self._lock:
            if self.report is not None:
                return self.report
            self.state = state
            self.record("finished", {"status": state.value, "speech": speech,
                                     "verified": False, "label_source": None})
            self.report = {
                "session_id": self.session_id, "software": "h-company",
                "procedure_id": self.request.procedure_id, "goal": self.request.goal,
                "mode": self.request.mode, "autonomy": 2 if self.request.mode == "act" else 0,
                "takeover": self.request.mode == "act", "status": state.value,
                "declared": {"outcome": "done" if state is _State.completed else
                             "blocked" if state is _State.blocked else "unclear", "summary": speech},
                "verification": {"performed": False, "satisfied": False,
                                 "observed": "No independent task verification was performed."},
                "feedback": None, "escalation": None, "cost_usd": None,
                "timings": {"started_at": self._started_at, "finished_at": _now()},
                "simulated": False, "harness": "h-platform-coach-v2",
            }
            _write_private(self.runs_dir / "report.json", self.report)
            return self.report

    def add_feedback(self, feedback) -> None:
        """DesktopFeedback calls this only after writing explicit human labels."""
        with self._lock:
            if self.report is None or not self.state.terminal:
                raise ValueError("the session must be finished before feedback")
            label_path = self.runs_dir / "labels.json"
            if label_path.is_symlink():
                raise ValueError("human labels must belong to this private session")
            try:
                labels = json.loads(label_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError("save explicit human labels through DesktopFeedback first") from exc
            if (labels.get("session_id") != self.session_id or labels.get("label_source") != "human"
                    or labels.get("confirmed_by_human") is not True):
                raise ValueError("feedback requires explicit human confirmation")
            value = feedback.model_dump(mode="json")
            self.report["feedback"] = value
            self.record("human_feedback", value)
            _write_private(self.runs_dir / "report.json", self.report)
