"""Item 4: reliability metrics per scenario, real sessions only, honest N."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from hcs_backend.app import create_app
from hcs_backend.config import Settings
from hcs_backend.metrics import compute, scenario_metrics
from hcs_backend.store import Store

FIX = Path(__file__).parent / "fixtures"
GUIDE_OK = json.loads((FIX / "report_guide_resolved.json").read_text())
GUIDE_ESC = json.loads((FIX / "report_guide_escalated.json").read_text())
ACT_OK = json.loads((FIX / "report_act_resolved.json").read_text())


def real(r, case_id, **changes):
    r = copy.deepcopy(r)
    r.update(simulated=False, case_id=case_id, session_id=f"s-{case_id}", **changes)
    return r


def test_empty_metrics_are_none_not_zero():
    m = scenario_metrics([])
    assert m["n"] == 0 and m["success_rate"] is None and m["median_stop_latency_s"] is None


def test_per_scenario_numbers():
    take = real(GUIDE_OK, "g2")
    take["steps"].append({"index": 99, "attempt": 1, "timestamp": take["steps"][-1]["timestamp"], "kind": "action",
                          "summary": "autonomy raised to max: taking over"})
    stopped = real(ACT_OK, "a2", status="abandoned", cost_usd=0.4)
    stopped["verification"]["satisfied"] = None
    stopped["timings"].update(stop_requested_at="2026-11-07T21:38:28.000Z", stop_effective_at="2026-11-07T21:38:28.300Z")
    store = Store(":memory:")
    for r in (real(GUIDE_OK, "g1"), take, real(ACT_OK, "a1", cost_usd=0.2), stopped, GUIDE_ESC):  # last = simulated
        store.add_case(r)
    m = compute(store.list_cases())
    assert m["excluded_simulated"] == 1
    g = m["scenarios"]["odoo_crm_create_opportunity"]
    assert g["n"] == 2 and g["success_rate"] == 1.0 and g["takeover_rate"] == 0.5
    assert g["n_guided_steps"] == 6 and g["median_s_per_guided_step"] == 0.0
    a = m["scenarios"]["odoo_crm_followup_activity"]
    assert a["n"] == 2 and a["verified"] == 1 and a["success_rate"] == 0.5 and a["abandoned"] == 1
    assert abs(a["median_stop_latency_s"] - 0.3) < 1e-6 and abs(a["mean_cost_usd"] - 0.3) < 1e-9
    assert a["n_guided"] == 0 and a["takeover_rate"] is None
    assert m["overall"]["n"] == 4


def test_metrics_page_and_json_require_auth_and_show_n():
    c = TestClient(create_app(Settings(ingest_token="t", dashboard_password="pw"), Store(":memory:"), start_poller=False))
    assert c.get("/dashboard/metrics").status_code == 401 and c.get("/metrics").status_code == 401
    assert "No real session yet" in c.get("/dashboard/metrics", auth=("support", "pw")).text
    c.post("/cases", json=real(ACT_OK, "a1"), headers={"Authorization": "Bearer t"})
    c.post("/cases", json=GUIDE_OK, headers={"Authorization": "Bearer t"})
    html = c.get("/dashboard/metrics", auth=("support", "pw")).text
    assert "odoo_crm_followup_activity" in html and "100 %" in html and "(1/1)" in html
    assert "1 simulated session(s) excluded" in html
    assert c.get("/metrics", auth=("support", "pw")).json()["overall"]["n"] == 1
