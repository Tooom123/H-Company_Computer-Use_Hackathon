"""Item 5: escalation case file = goal, role, observed state, steps tried, exact blocker, Linkup context on the
blocker, evidence refs, decision expected (JSON, Markdown and a printable page)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from hcs_backend.app import create_app
from hcs_backend.config import Settings
from hcs_backend.escalation import build_escalation, escalation_markdown
from hcs_backend.store import Store

ESC = json.loads((Path(__file__).parent / "fixtures" / "report_guide_escalated.json").read_text())
AUTH = ("support", "pw")


def test_escalation_file_carries_blocker_documentation_and_course():
    store = Store(":memory:")
    case, _ = store.add_case(ESC)
    e = build_escalation(case)
    assert e["blocked_on"].startswith("Access Error") and e["decision_expected"]
    assert len(e["documentation"]) == 1 and e["documentation"][0]["sources"][0]["url"].startswith("https://")
    assert e["session_course"] and all(ev["phase"] != "system" for ev in e["session_course"])
    md = escalation_markdown(case)
    for needle in ("## Decision expected from support", "## What the documentation says about the blocker",
                   "## What happened", "## Evidence", "**Q:**", "- **Mode:** guide", "new sales rep"):
        assert needle in md, needle


def test_no_documentation_is_said_explicitly():
    r = json.loads(json.dumps(ESC))
    r["knowledge"] = []
    store = Store(":memory:")
    case, _ = store.add_case(r)
    assert "no documentation lookup on this blocker" in escalation_markdown(case)


def test_printable_dossier_page():
    c = TestClient(create_app(Settings(ingest_token="t", dashboard_password="pw"), Store(":memory:"), start_poller=False))
    c.post("/cases", json=ESC, headers={"Authorization": "Bearer t"})
    cid = ESC["case_id"]
    assert c.get(f"/dashboard/cases/{cid}/dossier").status_code == 401
    html = c.get(f"/dashboard/cases/{cid}/dossier", auth=AUTH).text
    for needle in ("Escalation file", "Decision expected from support", "Exact blocker", "What happened",
                   "What the documentation says about the blocker", "Print / save as PDF", "SIMULATED"):
        assert needle in html, needle
    assert f"/dashboard/cases/{cid}/dossier" in c.get(f"/dashboard/cases/{cid}", auth=AUTH).text
