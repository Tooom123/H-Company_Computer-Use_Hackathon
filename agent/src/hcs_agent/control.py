"""Local control point for the H Companion desktop app (desktop/), served by `talk` and `run`.

The app is a window next to the work, like a dictation app: it shows what the assistant is doing, holds the
autonomy setting (the on-screen Magnet hides while the app is open), stops a task, sets the voice, and shows
usage and costs. This module is the only bridge: plain HTTP on 127.0.0.1, stdlib only, no key ever sent.

    GET  /status     live state: voice, current task (step, takeover, cost), autonomy, speech
    GET  /sessions   last reports in runs/ (newest first)
    GET  /usage      sessions this month, H spend and concurrency, ElevenLabs characters, keys configured
    POST /autonomy   {"level": 0|1|2}
    POST /stop       stop the current task (local gate first, as everywhere)
    POST /next       {"session_id": ..., "step_index": ..., "done": bool} explicit user report, not verification
    POST /voice      {"enabled"?: bool, "voice"?: id, "speed"?: float}
    POST /voice/test say a sample sentence
    GET  /feedback   current completed-session feedback draft
    POST /feedback/dictate {"session_id": ...} arm the next transcript as feedback
    POST /feedback  explicit human labels, bound to a finished session
    POST /rate       {"id": run folder, "useful": true | false | null} the user's verdict on a finished task
    POST /ptt        {"key": "cmd+h" | "cmd+j" | "alt_r" | "f9"} push-to-talk key, live

Safety: bound to 127.0.0.1; every request must carry `X-HCS-App: 1` (a web page cannot add that header to a
cross-origin request without a CORS preflight, which is never granted) and a local Host header (DNS rebinding).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from typing import Any, Callable

from .desktop_feedback import DesktopFeedback, FeedbackError

DEFAULT_PORT = 8768
APP_HEADER = "X-HCS-App"
APP_TIMEOUT_S = 6.0  # the app polls every second; silent longer than this = closed, the Magnet comes back

AUTONOMY_LABELS = ("Show me", "Help if I'm stuck", "Do it, I watch")
AUTONOMY_HINTS = (
    "I point at each control and explain. You click; I never take the controls.",
    "I guide you. If you are stuck twice on a step, or ask me, I finish it myself and narrate.",
    "I do the task in front of you and annotate every action. Stop at any time.",
)
VOICES = (  # premade ElevenLabs voices (every account has them), all with a plain American accent
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "note": "warm, reassuring"},
    {"id": "cgSgspJ2msm6clMCkdW9", "name": "Jessica", "note": "bright, playful"},
    {"id": "hpp4J3VqNfWAUOO0d1Us", "name": "Bella", "note": "professional, warm"},
    {"id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda", "note": "upbeat, knowledgeable"},
)
# Push-to-talk keys the InputHub handles on macOS (combo = swallowed, plain key = held alone).
PTT_KEYS = (
    {"key": "ctrl+shift+h", "label": "⌃⇧H"},
    {"key": "cmd+h", "label": "⌘H"},
    {"key": "cmd+j", "label": "⌘J"},
    {"key": "alt_r", "label": "Right ⌥"},
    {"key": "f9", "label": "F9"},
)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def read_reports(runs_dir: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Compact summaries of runs/*/report.json, newest first. Unreadable or half-written files are skipped."""
    files = sorted(runs_dir.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for f in files:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        t = r.get("timings") or {}
        a, b = _parse_ts(t.get("approved_at") or t.get("started_at")), _parse_ts(t.get("finished_at"))
        v = r.get("verification") or {}
        esc = r.get("escalation") or {}
        fb = r.get("feedback") or {}
        out.append({
            "id": f.parent.name,  # the folder: what /rate takes
            "useful": fb.get("useful"),
            "session_id": r.get("session_id") or f.parent.name,
            "case_id": r.get("case_id"),
            "procedure_id": r.get("procedure_id"),
            "goal": r.get("goal"),
            "mode": r.get("mode"),
            "status": r.get("status"),
            "verified": v.get("satisfied") is True,
            "blocked_on": esc.get("blocked_on"),
            "started_at": t.get("started_at"),
            "duration_s": round((b - a).total_seconds(), 1) if a and b else None,
            "cost_usd": r.get("cost_usd"),
            "simulated": bool(r.get("simulated")),
        })
        if limit and len(out) >= limit:
            break
    return out


def rate_session(runs_dir: Path, run_id: str, useful: bool | None) -> dict[str, Any]:
    """The user's verdict on a finished task (✓ useful / ✗ not useful / None = cleared), written into the
    report's `feedback` (user-declared, never inferred) and sent again to the support backend, which updates
    the case: material for debugging and for learning which tasks went well."""
    if not re.fullmatch(r"[\w-]{1,80}", run_id or ""):
        raise ValueError("bad id")
    f = runs_dir / run_id / "report.json"
    if not f.is_file():
        raise FileNotFoundError(run_id)
    data = json.loads(f.read_text(encoding="utf-8"))
    fb = dict(data.get("feedback") or {})
    fb["useful"] = useful
    fb.setdefault("comment", None)
    fb.setdefault("allow_screenshots_to_support", False)
    data["feedback"] = fb
    tmp = f.with_suffix(".json.part")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)
    sent = False
    try:
        from .contract import InterventionReport
        from .support import shared_uplink

        up = shared_uplink()
        if up is not None:
            up.send_report(InterventionReport.model_validate(data))
            sent = True
    except Exception:  # noqa: BLE001 - the verdict is saved locally either way
        pass
    return {"id": run_id, "useful": useful, "sent_to_support": sent}


def month_usage(reports: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """This calendar month (UTC). Real sessions only for the plan and the spend; simulated counted apart."""
    now = now or datetime.now(timezone.utc)
    this_month = [r for r in reports
                  if (d := _parse_ts(r.get("started_at"))) and (d.year, d.month) == (now.year, now.month)]
    real = [r for r in this_month if not r["simulated"]]
    costs = [float(r["cost_usd"]) for r in real if r.get("cost_usd") is not None]
    return {
        "month": now.strftime("%Y-%m"),
        "sessions": len(real),
        "verified": sum(1 for r in real if r["verified"]),
        "escalated": sum(1 for r in real if r["status"] == "escalated"),
        "simulated": len(this_month) - len(real),
        "median_duration_s": median(durs) if (durs := [r["duration_s"] for r in real if r["duration_s"]]) else None,
        "h_spend_usd": round(sum(costs), 4) if costs else 0.0,
        "h_cost_per_session_usd": round(sum(costs) / len(costs), 4) if costs else None,
    }


class _Cached:
    """A slow external read (quota, subscription) refreshed at most every `ttl` seconds; errors become None."""

    def __init__(self, fetch: Callable[[], Any], ttl: float = 60.0) -> None:
        self.fetch, self.ttl = fetch, ttl
        self.value: Any = None
        self.at = 0.0
        self.lock = threading.Lock()

    def get(self) -> Any:
        with self.lock:
            if time.time() - self.at > self.ttl:
                try:
                    self.value = self.fetch()
                except Exception:  # noqa: BLE001 - offline or no key: show "unknown", never fail the page
                    self.value = None
                self.at = time.time()
            return self.value


def h_quota() -> dict[str, Any] | None:
    import httpx
    from hai_agents.client import default_api_key

    base = os.environ.get("HAI_BASE_URL", "https://agp.eu.hcompany.ai").rstrip("/")
    r = httpx.get(f"{base}/api/v2/sessions/quota", headers={"Authorization": f"Bearer {default_api_key()}"},
                  timeout=5)
    r.raise_for_status()
    q = r.json()
    return {"active": q.get("active"), "limit": q.get("limit")}


def elevenlabs_usage() -> dict[str, Any] | None:
    import httpx

    from .speech import _api_key

    key = _api_key()
    if not key:
        return None
    r = httpx.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}, timeout=5)
    r.raise_for_status()
    s = r.json()
    reset = s.get("next_character_count_reset_unix")
    return {"tier": s.get("tier"), "characters_used": s.get("character_count"),
            "characters_limit": s.get("character_limit"),
            "resets_at": datetime.fromtimestamp(reset, timezone.utc).isoformat() if reset else None}


class Controller:
    """What the app may read and do. The CLI fills the callbacks; everything here is thread-safe."""

    def __init__(self, runs_dir: Path, *, status: Callable[[], dict[str, Any]],
                 set_autonomy: Callable[[int], None], stop: Callable[[], bool],
                 set_voice: Callable[[dict[str, Any]], dict[str, Any]], test_voice: Callable[[], bool],
                 set_ptt_key: Callable[[str], bool] = lambda _k: False,
                 on_app_presence: Callable[[bool], None] | None = None,
                 feedback: DesktopFeedback | None = None,
                 next_step: Callable[[str, int, bool], bool] | None = None,
                 quota: Callable[[], Any] = h_quota, tts_usage: Callable[[], Any] = elevenlabs_usage) -> None:
        self.runs_dir = runs_dir
        self._status, self._set_autonomy, self._stop = status, set_autonomy, stop
        self._set_voice, self._test_voice, self._set_ptt = set_voice, test_voice, set_ptt_key
        self._on_presence = on_app_presence
        self._feedback = feedback or DesktopFeedback()
        self._next_step = next_step
        self._next_lock = threading.Lock()
        self._quota, self._tts = _Cached(quota), _Cached(tts_usage)
        self.app_seen = 0.0
        self.app_present = False
        self.app_bounds: tuple[float, float, float, float] | None = None  # app window, top-left screen points
        self._lock = threading.Lock()

    # The app's polling is its heartbeat: present while it polls, gone after APP_TIMEOUT_S of silence.
    def seen(self, bounds: tuple[float, float, float, float] | None = None) -> None:
        with self._lock:
            self.app_seen = time.time()
            self.app_bounds = bounds  # hidden app keeps polling without bounds; its old rectangle must not consume clicks
            changed = not self.app_present
            self.app_present = True
        if changed and self._on_presence:
            self._on_presence(True)

    def check_presence(self) -> None:
        with self._lock:
            gone = self.app_present and time.time() - self.app_seen > APP_TIMEOUT_S
            if gone:
                self.app_present = False
        if gone and self._on_presence:
            self._on_presence(False)

    def app_contains(self, x: float, y: float) -> bool:
        """A click in the app window is the user steering the assistant, not the user doing the step."""
        b = self.app_bounds
        if not self.app_present or b is None:
            return False
        return b[0] <= x <= b[0] + b[2] and b[1] <= y <= b[1] + b[3]

    def status(self) -> dict[str, Any]:
        s = dict(self._status())
        s["app_connected"] = self.app_present
        s["autonomy_labels"] = list(AUTONOMY_LABELS)
        s["autonomy_hints"] = list(AUTONOMY_HINTS)
        s["voices"] = list(VOICES)
        s["ptt_keys"] = list(PTT_KEYS)
        return s

    def usage(self) -> dict[str, Any]:
        reports = read_reports(self.runs_dir)
        return {
            "month": month_usage(reports),
            "h_quota": self._quota.get(),
            "elevenlabs": self._tts.get(),
            "configured": {name: bool(os.environ.get(var)) for name, var in
                           (("h", "HAI_API_KEY"), ("gladia", "GLADIA_API_KEY"), ("linkup", "LINKUP_API_KEY"))},
        }

    def handle(self, method: str, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        path = path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/feedback", "/feedback/dictate"):
            try:
                if method == "GET" and path == "/feedback":
                    return 200, self._feedback.status()
                if method == "POST" and path == "/feedback/dictate":
                    return 200, self._feedback.arm(body)
                if method == "POST" and path == "/feedback":
                    return 200, self._feedback.save(body)
            except FeedbackError as exc:
                return exc.status, {"error": str(exc)}
            return 405, {"error": "Method not allowed"}
        if method == "GET" and path == "/status":
            return 200, self.status()
        if method == "GET" and path == "/sessions":
            return 200, {"sessions": read_reports(self.runs_dir, limit=30)}
        if method == "GET" and path == "/usage":
            return 200, self.usage()
        if method == "POST" and path == "/autonomy":
            level = body.get("level")
            if not isinstance(level, int) or isinstance(level, bool) or level not in (0, 1, 2):
                return 400, {"error": "level must be 0, 1 or 2"}
            if level != 0 and os.environ.get("HCS_GUIDE_OBSERVE_ONLY") == "1":
                return 403, {"error": "This coaching session only observes; autonomous control is disabled"}
            self._set_autonomy(level)
            return 200, self.status()
        if method == "POST" and path == "/stop":
            return 200, {"stopped": self._stop()}
        if method == "POST" and path == "/next":
            sid, index, done = body.get("session_id"), body.get("step_index"), body.get("done")
            if (not isinstance(sid, str) or not sid or len(sid) > 128
                    or type(index) is not int or index < 1 or type(done) is not bool):
                return 400, {"error": "session_id, positive step_index and boolean done are required"}
            with self._next_lock:
                if self._next_step is None or not self._next_step(sid, index, done):
                    return 409, {"error": "This step is no longer awaiting your response"}
            return 200, {"accepted": True, "verified": False}
        if method == "POST" and path == "/voice":
            allowed = {k: body[k] for k in ("enabled", "voice", "speed", "response_mode") if k in body}
            if "response_mode" in allowed and allowed["response_mode"] not in ("text", "voice", "both"):
                return 400, {"error": "response_mode must be text, voice or both"}
            if "enabled" in allowed and not isinstance(allowed["enabled"], bool):
                return 400, {"error": "enabled must be true or false"}
            if "voice" in allowed and allowed["voice"] not in {v["id"] for v in VOICES}:
                return 400, {"error": "unknown voice"}
            if "speed" in allowed:
                try:
                    allowed["speed"] = min(1.2, max(0.7, float(allowed["speed"])))
                except (TypeError, ValueError):
                    return 400, {"error": "speed must be a number"}
            return 200, self._set_voice(allowed)
        if method == "POST" and path == "/rate":
            useful = body.get("useful")
            if useful is not None and not isinstance(useful, bool):
                return 400, {"error": "useful must be true, false or null"}
            try:
                return 200, rate_session(self.runs_dir, str(body.get("id") or ""), useful)
            except ValueError:
                return 400, {"error": "bad id"}
            except FileNotFoundError:
                return 404, {"error": "no such task"}
        if method == "POST" and path == "/ptt":
            key = body.get("key")
            if key not in {k["key"] for k in PTT_KEYS}:
                return 400, {"error": "unknown key"}
            if not self._set_ptt(key):
                return 409, {"error": "push-to-talk runs with `hcs-agent talk` only"}
            return 200, self.status()
        if method == "POST" and path == "/voice/test":
            return 200, {"spoken": self._test_voice()}
        return 404, {"error": "not found"}


def _bounds(value: str | None) -> tuple[float, float, float, float] | None:
    try:
        x, y, w, h = (float(v) for v in (value or "").split(","))
    except ValueError:
        return None
    return (x, y, w, h) if w > 0 and h > 0 else None


def _handler(ctl: Controller) -> type[BaseHTTPRequestHandler]:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # quiet: the app polls every second
            pass

        def _reply(self, code: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _serve(self, method: str) -> None:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost") or self.headers.get(APP_HEADER) != "1":
                self._reply(403, {"error": "forbidden"})
                return
            body: dict[str, Any] = {}
            if method == "POST":
                try:
                    n = min(int(self.headers.get("Content-Length") or 0), 10_000)
                    body = json.loads(self.rfile.read(n) or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError
                except ValueError:
                    self._reply(400, {"error": "JSON object expected"})
                    return
            ctl.seen(_bounds(self.headers.get("X-HCS-App-Bounds")))
            try:
                code, payload = ctl.handle(method, self.path, body)
            except Exception as exc:  # noqa: BLE001 - one bad request must not kill the agent
                code, payload = 500, {"error": str(exc)[:200]}
            self._reply(code, payload)

        def do_GET(self) -> None:  # noqa: N802
            self._serve("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._serve("POST")

    return H


class ControlServer:
    def __init__(self, ctl: Controller, port: int = DEFAULT_PORT) -> None:
        self.ctl = ctl
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler(ctl))
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._stop = threading.Event()

    def start(self) -> "ControlServer":
        threading.Thread(target=self.httpd.serve_forever, name="hcs-control", daemon=True).start()

        def watch() -> None:
            while not self._stop.wait(1.0):
                self.ctl.check_presence()

        threading.Thread(target=watch, name="hcs-control-presence", daemon=True).start()
        return self

    def close(self) -> None:
        self._stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()
