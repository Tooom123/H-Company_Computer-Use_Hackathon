"""Private desktop run journal and explicit human feedback, shared by talk and its control API."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import FeedbackCommand


class FeedbackError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _json_file(path: Path, data: dict, *, exclusive: bool = False) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode()
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
        return
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(payload)
    tmp.replace(path)


class RunJournal:
    """A separate session directory; never overwrite an older attempt or follow a supplied path."""

    def __init__(self, root: Path, request, sink, *, simulated: bool = False):
        sid = request.session_id
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", sid):
            raise ValueError("Invalid session ID")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory = root / sid
        self.directory.mkdir(mode=0o700)  # a reused ID must fail before any action
        self._sink, self._lock = sink, threading.Lock()
        _json_file(self.directory / "request.json", request.model_dump(mode="json"), exclusive=True)
        now = datetime.now(timezone.utc).isoformat()
        self._episode = {"id": sid, "scenario_id": "H-LIVE" if request.software == "h-company" else request.procedure_id,
                         "source": request.software, "software": request.software, "goal": request.goal,
                         "mode": request.mode.value, "human_present": True, "simulated": bool(simulated),
                         "state": "created", "created_at": now, "updated_at": now, "export_status": "pending"}
        _json_file(self.directory / "episode.json", self._episode, exclusive=True)

    def __call__(self, event):
        line = (json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n").encode()
        with self._lock:
            fd = os.open(self.directory / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "ab") as out:
                out.write(line)
            self._episode.update(state=event.state.value, updated_at=datetime.now(timezone.utc).isoformat())
            if event.state.terminal:
                self._episode.setdefault("finished_at", self._episode["updated_at"])
            _json_file(self.directory / "episode.json", self._episode)
        self._sink(event)


class DesktopFeedback:
    """Only known, completed interventions may receive human labels. Dictation never routes a task."""

    def __init__(self):
        self._lock = threading.RLock()
        self._interventions: dict[str, Any] = {}
        self._drafts: dict[str, str] = {}
        self._current: str | None = None
        self._selected: str | None = None
        self._armed: str | None = None

    def register(self, intervention):
        with self._lock:
            sid = intervention.request.session_id
            self._interventions[sid] = intervention
            self._current = sid
            # A new request must never erase an unsubmitted comment for an earlier session.
            if self._selected not in self._drafts or self._saved(self._selected):
                self._selected = sid
            self._armed = None

    def _saved(self, sid):
        it = self._interventions.get(sid)
        return bool(it and (it.runs_dir / "labels.json").is_file())

    def _finished(self, sid):
        if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", sid):
            raise FeedbackError(400, "A valid session_id is required")
        it = self._interventions.get(sid)
        if it is None:
            raise FeedbackError(404, "Unknown session")
        if not it.state.terminal or it.report is None:
            raise FeedbackError(409, "Wait until this session has finished")
        return it

    def status(self):
        with self._lock:
            if self._selected != self._current and self._saved(self._selected):
                self._selected = self._current
            return self._status_for(self._selected)

    def _status_for(self, sid):
        with self._lock:
            it = self._interventions.get(sid)
            return {"session_id": sid, "available": bool(it and it.state.terminal and it.report is not None),
                    "dictation_armed": self._armed == sid and sid is not None,
                    "comment": self._drafts.get(sid, ""), "saved": self._saved(sid)}

    def arm(self, body):
        with self._lock:
            sid = body.get("session_id")
            self._finished(sid)
            if self._saved(sid):
                raise FeedbackError(409, "Feedback already saved")
            current = self._interventions.get(self._current)
            if current and not current.state.terminal:
                raise FeedbackError(409, "Wait until the active task has finished before dictating feedback")
            self._selected = self._armed = sid
            return self.status()

    def consume_transcript(self, text: str) -> bool:
        with self._lock:
            if self._armed is None:
                return False
            sid, self._armed = self._armed, None
            it = self._finished(sid)
            self._drafts[sid] = text
            _json_file(it.runs_dir / "feedback-draft.json", {"session_id": sid, "comment": text,
                       "source": "human_voice_transcription", "confirmed_by_human": False})
            return True

    def save(self, body):
        with self._lock:
            sid = body.get("session_id")
            it = self._finished(sid)
            success, useful, comment = body.get("success"), body.get("useful"), body.get("comment")
            if success not in ("yes", "partial", "no", "unknown") or useful not in ("yes", "no", "unknown"):
                raise FeedbackError(400, "Choose success and usefulness explicitly")
            if not isinstance(comment, str) or len(comment) > 4000:
                raise FeedbackError(400, "Comment must be text of at most 4000 characters")
            if body.get("confirmed_by_human") is not True:
                raise FeedbackError(400, "Human confirmation is required")
            if body.get("allow_screenshots_to_support") is not False or body.get("training_consent") is not False:
                raise FeedbackError(400, "This local trial does not enable screenshot sharing or training")
            labels = {"session_id": sid, "success": success, "useful": useful, "comment": comment,
                      "task_success_user": {"yes": "success", "partial": "partial", "no": "failure", "unknown": "unknown"}[success],
                      "label_source": "human", "confirmed_by_human": True, "user_confirmed": True,
                      "confirmed_at": datetime.now(timezone.utc).isoformat(),
                      "allow_screenshots_to_support": False, "training_consent": False, "allow_training": False,
                      "include_for_training": False, "ready_for_sft": False, "reviewed": False,
                      "simulated": bool(it.backend.simulated)}
            try:
                _json_file(it.runs_dir / "labels.json", labels, exclusive=True)
            except FileExistsError:
                raise FeedbackError(409, "Feedback already saved") from None
            it.add_feedback(FeedbackCommand(useful={"yes": True, "no": False, "unknown": None}[useful],
                                           comment=comment, allow_screenshots_to_support=False))
            self._selected = sid
            self._drafts[sid] = comment
            self._armed = None
            return self._status_for(sid)
