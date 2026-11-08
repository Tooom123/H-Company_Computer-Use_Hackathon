"""Desktop app control point: routes, validation, safety headers, app presence, reports. No key, no network."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hcs_agent import control
from hcs_agent.control import ControlServer, Controller, month_usage, read_reports


def _report(d: Path, sid: str, *, status="resolved", verified=True, cost=0.5, simulated=False,
            started="2026-11-08T10:00:00Z", finished="2026-11-08T10:01:30Z") -> None:
    (d / sid).mkdir(parents=True)
    (d / sid / "report.json").write_text(json.dumps({
        "session_id": sid, "case_id": "c-" + sid, "procedure_id": "odoo_crm_create_opportunity", "goal": "g",
        "mode": "guide", "status": status, "verification": {"satisfied": verified},
        "escalation": {"blocked_on": "Won refused"} if status == "escalated" else None,
        "timings": {"started_at": started, "approved_at": started, "finished_at": finished},
        "cost_usd": cost, "simulated": simulated}))


class Rig:
    def __init__(self, runs: Path) -> None:
        self.level = 1
        self.stopped = 0
        self.voice: dict = {}
        self.tested = 0
        self.presence: list[bool] = []
        self.ptt: list[str] = []
        self.ptt_ok = True
        self.ctl = Controller(
            runs, status=lambda: {"autonomy": self.level, "current": None},
            set_autonomy=self._set, stop=self._stop, set_voice=self._voice, test_voice=self._test,
            set_ptt_key=self._ptt,
            on_app_presence=self.presence.append, quota=lambda: {"active": 1, "limit": 3},
            tts_usage=lambda: {"tier": "creator", "characters_used": 10, "characters_limit": 100})
        self.srv = ControlServer(self.ctl, port=0).start()
        self.base = f"http://127.0.0.1:{self.srv.port}"

    def _set(self, level):
        self.level = level

    def _stop(self):
        self.stopped += 1
        return True

    def _voice(self, opts):
        self.voice.update(opts)
        return dict(self.voice)

    def _ptt(self, key):
        self.ptt.append(key)
        return self.ptt_ok

    def _test(self):
        self.tested += 1
        return True

    def call(self, method: str, path: str, body=None, headers=None):
        h = {"X-HCS-App": "1", "Content-Type": "application/json"} if headers is None else headers
        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    yield r
    r.srv.close()


def test_status_carries_labels_and_presence(rig):
    code, s = rig.call("GET", "/status")
    assert code == 200 and s["autonomy"] == 1 and s["app_connected"] is True
    assert s["autonomy_labels"] == ["Show me", "Help if I'm stuck", "Do it, I watch"]
    assert {v["name"] for v in s["voices"]} >= {"Sarah", "Jessica"}


def test_requests_without_the_app_header_are_refused(rig):
    code, _ = rig.call("POST", "/stop", {}, headers={"Content-Type": "text/plain"})
    assert code == 403 and rig.stopped == 0  # a web page cannot stop the agent behind the user's back
    req = urllib.request.Request(rig.base + "/status", headers={"X-HCS-App": "1", "Host": "evil.example"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 403  # DNS rebinding


def test_autonomy_is_validated(rig):
    assert rig.call("POST", "/autonomy", {"level": 2})[0] == 200 and rig.level == 2
    for bad in (3, -1, "2", True, None):
        assert rig.call("POST", "/autonomy", {"level": bad})[0] == 400
    assert rig.level == 2
    assert rig.call("POST", "/autonomy", [1])[0] == 400  # not an object


def test_stop_and_voice(rig):
    assert rig.call("POST", "/stop")[1] == {"stopped": True} and rig.stopped == 1
    code, v = rig.call("POST", "/voice", {"enabled": False, "voice": "cgSgspJ2msm6clMCkdW9", "speed": 9})
    assert code == 200 and v == {"enabled": False, "voice": "cgSgspJ2msm6clMCkdW9", "speed": 1.2}
    assert rig.call("POST", "/voice", {"voice": "someone-else"})[0] == 400
    assert rig.call("POST", "/voice", {"enabled": "yes"})[0] == 400
    assert rig.call("POST", "/voice/test")[1] == {"spoken": True} and rig.tested == 1
    assert rig.call("GET", "/nope")[0] == 404


def test_next_is_explicit_bound_to_step_and_never_claims_verification(rig):
    calls = []

    def next_step(sid, index, done):
        calls.append((sid, index, done))
        return (sid, index) == ("session-a", 2)

    rig.ctl._next_step = next_step
    for done in (True, False):
        assert rig.call("POST", "/next", {
            "session_id": "session-a", "step_index": 2, "done": done,
        }) == (200, {"accepted": True, "verified": False})
    assert calls == [("session-a", 2, True), ("session-a", 2, False)]
    assert rig.call("POST", "/next", {
        "session_id": "old-session", "step_index": 1, "done": True,
    })[0] == 409
    before = len(calls)
    for body in ({}, {"session_id": "session-a", "step_index": True, "done": True},
                 {"session_id": "session-a", "step_index": 0, "done": True},
                 {"session_id": "session-a", "step_index": 2, "done": "yes"}):
        assert rig.call("POST", "/next", body)[0] == 400
    assert len(calls) == before
    assert rig.call("POST", "/next", {
        "session_id": "session-a", "step_index": 2, "done": True,
    }, headers={"Content-Type": "application/json"})[0] == 403


def test_app_presence_hides_then_brings_back_the_magnet(rig, monkeypatch):
    rig.call("GET", "/status")
    assert rig.presence == [True]
    rig.call("GET", "/status")
    assert rig.presence == [True]  # once per change, not per poll
    monkeypatch.setattr(control, "APP_TIMEOUT_S", 0.1)
    time.sleep(0.2)
    rig.ctl.check_presence()
    assert rig.presence == [True, False]


def test_sessions_and_usage(rig, tmp_path):
    _report(tmp_path, "s1", cost=0.4)
    time.sleep(0.01)
    _report(tmp_path, "s2", status="escalated", verified=False, cost=0.6)
    _report(tmp_path, "s3", simulated=True, cost=0.0)
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "report.json").write_text("")  # half-written file: skipped
    code, body = rig.call("GET", "/sessions")
    assert code == 200 and {s["session_id"] for s in body["sessions"]} == {"s1", "s2", "s3"}
    s2 = next(s for s in body["sessions"] if s["session_id"] == "s2")
    assert s2["duration_s"] == 90.0 and s2["blocked_on"] == "Won refused" and not s2["verified"]
    code, u = rig.call("GET", "/usage")
    m = month_usage(read_reports(tmp_path), datetime(2026, 11, 20, tzinfo=timezone.utc))
    assert m == {"month": "2026-11", "sessions": 2, "verified": 1, "escalated": 1, "simulated": 1,
                 "median_duration_s": 90.0, "h_spend_usd": 1.0, "h_cost_per_session_usd": 0.5}
    assert u["h_quota"] == {"active": 1, "limit": 3} and u["elevenlabs"]["tier"] == "creator"
    assert set(u["configured"]) == {"h", "gladia", "linkup"}
    assert "key" not in json.dumps(u).lower().replace("api_key", "")  # never a secret in the payload


def test_other_months_do_not_count(tmp_path):
    _report(tmp_path, "old", started="2026-10-31T23:00:00Z", finished="2026-10-31T23:01:00Z")
    m = month_usage(read_reports(tmp_path), datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert m["sessions"] == 0 and m["h_cost_per_session_usd"] is None


def test_failing_external_reads_show_unknown(tmp_path):
    def boom():
        raise RuntimeError("offline")

    ctl = Controller(tmp_path, status=dict, set_autonomy=lambda _: None, stop=lambda: False,
                     set_voice=lambda o: o, test_voice=lambda: False, quota=boom, tts_usage=boom)
    u = ctl.usage()
    assert u["h_quota"] is None and u["elevenlabs"] is None


def test_push_to_talk_key(rig):
    code, s = rig.call("POST", "/ptt", {"key": "alt_r"})
    assert code == 200 and rig.ptt == ["alt_r"] and {k["key"] for k in s["ptt_keys"]} >= {"cmd+h", "alt_r"}
    assert rig.call("POST", "/ptt", {"key": "ctrl+shift+h"})[0] == 200
    assert rig.ptt[-1] == "ctrl+shift+h"
    assert rig.call("POST", "/ptt", {"key": "cmd+q"})[0] == 400  # never a key that quits apps
    rig.ptt_ok = False
    assert rig.call("POST", "/ptt", {"key": "f9"})[0] == 409  # `run` has no push-to-talk


def test_clicks_in_the_app_window_are_not_user_steps(rig):
    req = urllib.request.Request(rig.base + "/status", headers={"X-HCS-App": "1", "X-HCS-App-Bounds": "100,50,900,600"})
    urllib.request.urlopen(req, timeout=5).read()
    assert rig.ctl.app_contains(500, 300) and not rig.ctl.app_contains(50, 300)
    rig.call("GET", "/status", headers={"X-HCS-App": "1", "X-HCS-App-Bounds": "garbage"})
    assert rig.ctl.app_bounds is None  # no trustworthy visible bounds: never keep a stale exclusion rectangle
    rig.ctl.app_present = False
    assert not rig.ctl.app_contains(500, 300)  # app closed: every click counts again


def test_key_labels():
    from hcs_agent.cli import _key_label

    assert [_key_label(k) for k in ("cmd+h", "cmd+j", "alt_r", "f9", None)] == ["⌘H", "⌘J", "Right ⌥", "F9", "⌘H"]


def test_rate_a_task(rig, tmp_path):
    _report(tmp_path, "s1")
    code, r = rig.call("POST", "/rate", {"id": "s1", "useful": False})
    assert code == 200 and r["useful"] is False
    saved = json.loads((tmp_path / "s1" / "report.json").read_text())
    assert saved["feedback"] == {"useful": False, "comment": None, "allow_screenshots_to_support": False}
    assert saved["status"] == "resolved"  # only the user's verdict changes, never what was observed
    assert rig.call("GET", "/sessions")[1]["sessions"][0]["useful"] is False
    assert rig.call("POST", "/rate", {"id": "s1", "useful": None})[1]["useful"] is None
    assert rig.call("POST", "/rate", {"id": "../etc", "useful": True})[0] == 400
    assert rig.call("POST", "/rate", {"id": "nope", "useful": True})[0] == 404
    assert rig.call("POST", "/rate", {"id": "s1", "useful": "yes"})[0] == 400


def test_hidden_app_heartbeat_clears_click_exclusion_without_disconnect(tmp_path):
    ctl = Controller(tmp_path, status=dict, set_autonomy=lambda _: None, stop=lambda: False,
                     set_voice=dict, test_voice=lambda: False)
    ctl.seen((100, 50, 900, 600))
    assert ctl.app_contains(500, 300)
    ctl.seen(None)
    assert ctl.app_present and ctl.app_bounds is None
    assert not ctl.app_contains(500, 300)
