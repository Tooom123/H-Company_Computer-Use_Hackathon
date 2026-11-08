"""Optional uplink to the support backend (Tom's `hcs-backend`): forwards each report, and the live events,
so cases show up in the support dashboard as they happen.

Off unless `HCS_BACKEND_URL` is set. Never blocks or breaks an intervention: posts go through a background
thread with a short timeout; failures are logged once on stderr and the run goes on. The local
`runs/<session>/report.json` stays the source of truth.

    HCS_BACKEND_URL=http://127.0.0.1:8766     # backend base URL
    HCS_INGEST_TOKEN=...                      # same value as the backend's HCS_INGEST_TOKEN
    HCS_SUPPORT_USER=demo-user-1              # optional pseudonymous user ref (distinct users in the dashboard)
    HCS_SUPPORT_EVENTS=1                      # 0 = send the final report only, not the live events

The backend replaces a case when the same `case_id` is posted again, so the report is simply re-sent when
the user's feedback arrives.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .contract import AgentEvent, InterventionReport


class SupportUplink:
    def __init__(self, url: str, token: str, user_ref: str | None = None, send_events: bool = True,
                 timeout_s: float = 3.0, retries: int = 2) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.user_ref = user_ref
        self.send_events = send_events
        self.timeout_s = timeout_s
        self.retries = retries
        self.sent = 0
        self.failed = 0
        self._warned = False
        self._q: queue.Queue[tuple[str, dict[str, Any], int] | None] = queue.Queue()
        self._worker = threading.Thread(target=self._loop, name="support-uplink", daemon=True)
        self._worker.start()

    @classmethod
    def from_env(cls) -> SupportUplink | None:
        url = os.environ.get("HCS_BACKEND_URL", "").strip()
        if not url:
            return None
        return cls(url, os.environ.get("HCS_INGEST_TOKEN", ""), os.environ.get("HCS_SUPPORT_USER") or None,
                   send_events=os.environ.get("HCS_SUPPORT_EVENTS", "1") != "0")

    # ----------------------------------------------------------------------------------------- public
    def send_report(self, report: InterventionReport) -> None:
        self._q.put(("/cases", report.model_dump(mode="json"), self.retries))

    def send_event(self, event: AgentEvent) -> None:
        if self.send_events:
            self._q.put(("/events", event.model_dump(mode="json"), 0))  # live events: best effort, no retry

    def flush(self, timeout_s: float = 10.0) -> bool:
        """Wait until everything queued so far has been sent (or given up). Returns False on timeout."""
        done = threading.Event()
        self._q.put(("__flush__", {"done": done}, 0))
        return done.wait(timeout_s)

    # --------------------------------------------------------------------------------------- internals
    def _loop(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            path, body, retries = item
            if path == "__flush__":
                body["done"].set()
                continue
            for attempt in range(retries + 1):
                result = self._post(path, body)
                if result == "ok":
                    self.sent += 1
                    break
                if result == "rejected" or attempt == retries:
                    self.failed += 1
                    break
                time.sleep(0.5 * (attempt + 1))

    def _post(self, path: str, body: dict[str, Any]) -> str:
        """Returns ok, rejected (4xx: payload or token wrong, retrying will not help) or retry."""
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        if self.user_ref and path == "/cases":
            headers["X-HCS-User"] = self.user_ref
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return "ok" if 200 <= resp.status < 300 else "retry"
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            self._warn(f"{path} rejected ({e.code}): {detail}")
            return "rejected" if e.code < 500 else "retry"
        except (urllib.error.URLError, OSError) as e:
            self._warn(f"backend unreachable at {self.url} ({e})")
            return "retry"

    def _warn(self, msg: str) -> None:
        if not self._warned:
            print(f"[support] {msg} — the run continues, report kept locally", file=sys.stderr)
            self._warned = True


_shared: SupportUplink | None = None
_shared_init = False
_shared_lock = threading.Lock()


def shared_uplink() -> SupportUplink | None:
    """One uplink per process, configured from the environment (None when HCS_BACKEND_URL is unset)."""
    global _shared, _shared_init
    with _shared_lock:
        if not _shared_init:
            _shared, _shared_init = SupportUplink.from_env(), True
        return _shared
