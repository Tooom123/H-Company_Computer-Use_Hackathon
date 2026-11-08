"""Item 2: case timeline and new report fields, on real reports produced by the current engine (mock backend)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from hcs_backend.app import create_app
from hcs_backend.config import Settings
from hcs_backend.store import Store
from hcs_backend.timeline import (attempts, build_timeline, duration_s, guided_step_seconds, had_takeover,
                                  stop_latency_s)

FIX = Path(__file__).parent / "fixtures"
GUIDE_OK = json.loads((FIX / "report_guide_resolved.json").read_text())
GUIDE_ESC = json.loads((FIX / "report_guide_escalated.json").read_text())
ACT_OK = json.loads((FIX / "report_act_resolved.json").read_text())
TOKEN, AUTH = "t", ("support", "pw")


def client():
    s = Settings(ingest_token=TOKEN, dashboard_password="pw")
    return TestClient(create_app(s, Store(":memory:"), start_poller=False))


def post(c, r, user=None):
    h = {"Authorization": f"Bearer {TOKEN}"} | ({"X-HCS-User": user} if user else {})
    assert c.post("/cases", json=r, headers=h).status_code == 201


def test_guide_timeline_explains_steps_with_their_delay():
    tl = build_timeline(GUIDE_OK)
    explained = [e for e in tl if e["phase"] == "explain"]
    assert [e["step"] for e in explained] == [1, 2, 3]
    assert explained[0]["text"] == "Clique sur New" and explained[0]["detail"].startswith("Ça ouvre")
    assert guided_step_seconds(GUIDE_OK) == [0.4, 0.0, 0.0]
    assert any(e["phase"] == "system" for e in tl)  # grounding lines kept, but as detail
    assert tl[-1]["phase"] == "verify" and tl[-1]["final"] and "Postcondition observed" in tl[-1]["text"]
    assert not had_takeover(GUIDE_OK)


def test_act_timeline_separates_agent_actions_from_the_verifier():
    tl = build_timeline(ACT_OK)
    agent = [e for e in tl if e["actor"] == "agent"]
    verifier = [e for e in tl if e["actor"] == "verifier"]
    assert agent and all(e["phase"] in {"action", "observe"} for e in agent)
    assert [e["text"] for e in verifier[:3]] == ["[simulated] reload page", "[simulated] open opportunity",
                                                  "[simulated] read activities"]  # attempt 0 = verifier
    assert attempts(ACT_OK) == 1 and duration_s(ACT_OK) > 0 and stop_latency_s(ACT_OK) is None


def test_stuck_and_takeover_are_detected():
    r = copy.deepcopy(GUIDE_OK)
    r["steps"] += [
        {"index": 20, "attempt": 1, "timestamp": r["steps"][-1]["timestamp"], "kind": "action",
         "summary": "no progress after step 2 (miss 2); showing it again"},
        {"index": 21, "attempt": 1, "timestamp": r["steps"][-1]["timestamp"], "kind": "action",
         "summary": "autonomy raised to max: taking over"},
    ]
    phases = [e["phase"] for e in build_timeline(r)]
    assert "stuck" in phases and "takeover" in phases and had_takeover(r)


def test_attempts_use_the_engine_count_not_guide_step_numbers():
    assert attempts(GUIDE_ESC) == 1          # escalation.attempts, although steps carry attempt 1..3
    assert attempts(GUIDE_OK) is None        # guide mode without escalation: unknown, not guessed
    assert attempts(ACT_OK) == 1


def test_stop_latency_from_timings():
    r = copy.deepcopy(ACT_OK)
    r["timings"]["stop_requested_at"] = "2026-11-07T21:38:28.000000Z"
    r["timings"]["stop_effective_at"] = "2026-11-07T21:38:28.250000Z"
    assert abs(stop_latency_s(r) - 0.25) < 1e-6


def test_case_page_shows_timeline_knowledge_and_facts():
    c = client()
    post(c, GUIDE_ESC)
    html = c.get(f"/dashboard/cases/{GUIDE_ESC['case_id']}", auth=AUTH).text
    assert "Timeline" in html and "Documentation looked up (Linkup)" in html and "blocker" in html
    assert "mode: <b>guide</b>" in html and "takeover: <b>no</b>" in html and "SIMULATED" in html


def test_simulated_reports_are_excluded_from_dashboard_numbers():
    c = client()
    post(c, GUIDE_OK, "u1")                       # simulated
    real = copy.deepcopy(ACT_OK)
    real["simulated"], real["case_id"] = False, "real-1"
    post(c, real, "u2")
    html = c.get("/dashboard", auth=AUTH).text
    assert "1 simulated session(s) excluded from the numbers" in html
    assert "<b>1</b><span>real assisted sessions</span>" in html and "<b>1/1</b><span>verified resolved</span>" in html
