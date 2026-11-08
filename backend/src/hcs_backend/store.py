"""SQLite storage for cases (InterventionReports) and live AgentEvents.

Reports are stored verbatim as JSON next to a few indexed columns; nothing is rewritten, so what support
sees is exactly what the agent sent.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    received_at TEXT NOT NULL,
    user_ref    TEXT,
    simulated   INTEGER NOT NULL,
    demo_data   INTEGER NOT NULL,
    report      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cases_session ON cases(session_id);
CREATE TABLE IF NOT EXISTS events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT,
    session_id  TEXT NOT NULL,
    received_at TEXT NOT NULL,
    simulated   INTEGER NOT NULL,
    event       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_session ON events(session_id);
CREATE TABLE IF NOT EXISTS fixes (
    case_id     TEXT PRIMARY KEY,
    updated_at  TEXT NOT NULL,
    fix         TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class StoredCase:
    case_id: str
    session_id: str
    received_at: str
    user_ref: str | None
    simulated: bool
    demo_data: bool
    report: dict[str, Any]

    @property
    def user_key(self) -> str:
        """Who the case belongs to, for 'distinct users' counts. Falls back to the session."""
        return self.user_ref or f"session:{self.session_id}"


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    # cases -------------------------------------------------------------------------------------
    def add_case(self, report: dict[str, Any], user_ref: str | None = None) -> tuple[StoredCase, bool]:
        """Insert a report. Returns (case, created). Re-sending the same case_id replaces it
        (the agent may resend after feedback is added)."""
        report = dict(report)
        report.setdefault("case_id", uuid.uuid4().hex[:12])
        case_id = report["case_id"]
        with self._lock, self._db:
            existed = self._db.execute("SELECT 1 FROM cases WHERE case_id=?", (case_id,)).fetchone()
            received_at = now_iso()
            self._db.execute(
                "INSERT OR REPLACE INTO cases VALUES (?,?,?,?,?,?,?)",
                (
                    case_id,
                    report["session_id"],
                    received_at,
                    user_ref,
                    int(bool(report.get("simulated", False))),
                    int(bool(report.get("demo_data", True))),
                    json.dumps(report, ensure_ascii=False),
                ),
            )
        return self.get_case(case_id), not existed  # type: ignore[return-value]

    def get_case(self, case_id: str) -> StoredCase | None:
        row = self._db.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        return _case(row) if row else None

    def list_cases(self) -> list[StoredCase]:
        rows = self._db.execute("SELECT * FROM cases ORDER BY received_at, rowid").fetchall()
        return [_case(r) for r in rows]

    def delete_all(self, demo_only: bool = True) -> int:
        with self._lock, self._db:
            where = " WHERE demo_data=1" if demo_only else ""
            n = self._db.execute(f"DELETE FROM cases{where}").rowcount
            if not demo_only:
                self._db.execute("DELETE FROM events")
        return n

    # events ------------------------------------------------------------------------------------
    def add_event(self, event: dict[str, Any]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO events (event_id, session_id, received_at, simulated, event) VALUES (?,?,?,?,?)",
                (
                    event.get("event_id"),
                    event["session_id"],
                    now_iso(),
                    int(bool(event.get("simulated", False))),
                    json.dumps(event, ensure_ascii=False),
                ),
            )

    # fixes ---------------------------------------------------------------------------------------
    def recent_events(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute('SELECT event FROM events ORDER BY seq DESC LIMIT ?', (min(200, max(1, limit)),)).fetchall()
        return [json.loads(row['event']) for row in rows]

    def save_fix(self, fix: dict[str, Any]) -> None:
        fix = dict(fix)
        fix.setdefault("created_at", now_iso())
        fix["updated_at"] = now_iso()
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO fixes VALUES (?,?,?)",
                             (fix["case_id"], fix["updated_at"], json.dumps(fix, ensure_ascii=False)))

    def get_fix(self, case_id: str) -> dict[str, Any] | None:
        row = self._db.execute("SELECT fix FROM fixes WHERE case_id=?", (case_id,)).fetchone()
        return json.loads(row["fix"]) if row else None

    def list_fixes(self) -> list[dict[str, Any]]:
        return [json.loads(r["fix"]) for r in self._db.execute("SELECT fix FROM fixes ORDER BY updated_at DESC")]

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT event FROM events WHERE session_id=? ORDER BY seq", (session_id,)
        ).fetchall()
        return [json.loads(r["event"]) for r in rows]


def _case(row: sqlite3.Row) -> StoredCase:
    return StoredCase(
        case_id=row["case_id"],
        session_id=row["session_id"],
        received_at=row["received_at"],
        user_ref=row["user_ref"],
        simulated=bool(row["simulated"]),
        demo_data=bool(row["demo_data"]),
        report=json.loads(row["report"]),
    )
