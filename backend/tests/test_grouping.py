"""Item 3: grouping = same procedure + same category + similar (normalised) blocker."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from hcs_backend.app import create_app
from hcs_backend.config import Settings
from hcs_backend.grouping import group_cases, normalize
from hcs_backend.store import Store

ESC = json.loads((Path(__file__).parent / "fixtures" / "report_guide_escalated.json").read_text())


def variant(case_id, *, procedure=None, blocked_on=None, category=None, decision=None, satisfied="keep"):
    r = copy.deepcopy(ESC)
    r["case_id"], r["session_id"] = case_id, f"sess-{case_id}"
    if procedure:
        r["procedure_id"] = procedure
    if blocked_on:
        r["escalation"]["blocked_on"] = blocked_on
    if category:
        r["category"] = category
    if decision:
        r["escalation"]["decision_expected"] = decision
    if satisfied != "keep":
        r["verification"]["satisfied"] = satisfied
    return r


def grouped(reports):
    store = Store(":memory:")
    for r in reports:
        store.add_case(r)
    return group_cases(store.list_cases())


def test_normalize_drops_names_numbers_accents():
    a = normalize("Access Error: you are not allowed to modify 'Globex Démo' (id=42)")
    b = normalize("Access Error: you are not allowed to modify 'Umbrella Démo' (id=7)")
    assert a == b and "demo" not in a and "42" not in a


def test_two_similar_one_group_a_different_one_apart():
    gs = grouped([
        variant("a", blocked_on="Access Error: not allowed to modify 'Acme Demo' records"),
        variant("b", blocked_on="Access Error: not allowed to modify 'Globex Demo' records (attempt 2)"),
        variant("c", blocked_on="Stage 'Won' is missing from the pipeline"),
    ])
    sizes = sorted(len(g.cases) for g in gs)
    assert sizes == [1, 2]
    two = next(g for g in gs if len(g.cases) == 2)
    assert {c.case_id for c in two.cases} == {"a", "b"}


def test_same_blocker_other_procedure_or_category_stays_apart():
    same = "Access Error: not allowed to modify records"
    gs = grouped([variant("a", blocked_on=same), variant("b", blocked_on=same, procedure="odoo_crm_log_note"),
                  variant("c", blocked_on=same, category="configuration")])
    assert len(gs) == 3


def test_group_lists_cases_procedures_verified_results_and_decisions():
    gs = grouped([
        variant("a", blocked_on="Access Error: not allowed", decision="Grant the Sales manager right", satisfied=False),
        variant("b", blocked_on="Access Error: not allowed", decision="Reassign it for the user", satisfied=None),
    ])
    s = gs[0].summary()
    assert s["case_ids"] == ["a", "b"] and s["procedures"] == ["odoo_crm_change_stage_restricted"]
    assert s["verified"] == {"observed": 0, "not_observed": 1, "not_checked": 1}
    assert s["decisions_expected"] == ["Grant the Sales manager right", "Reassign it for the user"]


def test_group_page_shows_decisions_and_verified_results():
    c = TestClient(create_app(Settings(ingest_token="t", dashboard_password="pw"), Store(":memory:"), start_poller=False))
    for r in (variant("a", decision="Grant the Sales manager right"), variant("b")):
        c.post("/cases", json=r, headers={"Authorization": "Bearer t"})
    gid = c.get("/groups", auth=("support", "pw")).json()[0]["group_id"]
    html = c.get(f"/dashboard/groups/{gid}", auth=("support", "pw")).text
    assert "Decision(s) expected from support" in html and "Grant the Sales manager right" in html
    assert "Verified results" in html
