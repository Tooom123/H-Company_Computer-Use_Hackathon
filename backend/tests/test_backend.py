"""Backend tests: contract validation, auth, grouping (PRD acceptance), escalation file, dashboard."""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from hcs_backend.app import create_app
from hcs_backend.config import Settings
from hcs_backend.demo import demo_cases, resolved_activity
from hcs_backend.escalation import build_escalation, escalation_markdown
from hcs_backend.store import Store

TOKEN = "test-token"
AUTH = ("support", "pw")


@pytest.fixture
def client() -> TestClient:
    settings = Settings(ingest_token=TOKEN, dashboard_password="pw")
    return TestClient(create_app(settings, Store(":memory:")))


def post(client: TestClient, report: dict, user: str | None = None):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if user:
        headers["X-HCS-User"] = user
    return client.post("/cases", json=report, headers=headers)


def seed(client: TestClient) -> None:
    for report, user in demo_cases():
        assert post(client, report, user).status_code == 201


def test_demo_cases_match_contract(client):
    seed(client)
    assert len(client.get("/cases", auth=AUTH).json()) == 4


def test_ingest_requires_token(client):
    assert client.post("/cases", json=resolved_activity()).status_code == 401
    r = client.post("/cases", json=resolved_activity(), headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_read_and_dashboard_require_auth(client):
    seed(client)
    for path in ("/cases", "/groups", "/dashboard", "/dashboard/cases/demo-001", "/cases/demo-002/escalation.md"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, auth=("support", "wrong")).status_code == 401, path
        assert client.get(path, auth=AUTH).status_code == 200, path


def test_invalid_report_rejected(client):
    bad = resolved_activity()
    del bad["verification"]
    bad["status"] = "fixed-ish"
    r = post(client, bad)
    assert r.status_code == 422
    errors = " ".join(r.json()["detail"]["errors"])
    assert "verification" in errors and "status" in errors


def test_similar_cases_grouped_different_case_separate(client):
    """PRD: two similar cases share a problem, a different case stays distinct, sources are reachable."""
    seed(client)
    groups = client.get("/groups", auth=AUTH).json()
    by_case = {cid: g["group_id"] for g in groups for cid in g["case_ids"]}
    assert by_case["demo-002"] == by_case["demo-003"]
    assert by_case["demo-004"] != by_case["demo-002"]
    assert by_case["demo-001"] not in (by_case["demo-002"], by_case["demo-004"])
    perm = next(g for g in groups if g["group_id"] == by_case["demo-002"])
    assert perm["n_cases"] == 2 and perm["n_users"] == 2
    assert perm["category"] == "permissions"
    detail = client.get(f"/groups/{perm['group_id']}", auth=AUTH).json()
    assert {c["case_id"] for c in detail["cases"]} == {"demo-002", "demo-003"}


def test_same_text_other_category_not_grouped(client):
    a = resolved_activity()
    b = copy.deepcopy(a)
    b["case_id"], b["category"] = "other-cat", "configuration"
    post(client, a), post(client, b)
    groups = client.get("/groups", auth=AUTH).json()
    assert len(groups) == 2


def test_resend_replaces_case(client):
    r = resolved_activity()
    assert post(client, r).json()["created"] is True
    r["feedback"]["comment"] = "updated"
    assert post(client, r).json()["created"] is False
    assert client.get("/cases/demo-001", auth=AUTH).json()["report"]["feedback"]["comment"] == "updated"


def test_escalation_file_keeps_sources_apart_and_respects_consent():
    store = Store(":memory:")
    for report, user in demo_cases():
        store.add_case(report, user_ref=user)
    e = build_escalation(store.get_case("demo-002"))
    assert e["decision_expected"].startswith("Grant the user")
    assert e["agent_declared"]["outcome"] == "blocked"
    assert e["observed"]["postcondition_satisfied"] is False
    assert e["user_declared"]["goal"].startswith("Give the opportunity")
    assert e["evidence"] and e["evidence_withheld"] == 0  # demo-002 allows screenshots
    e3 = build_escalation(store.get_case("demo-003"))  # demo-003 did not allow screenshots
    assert e3["evidence"] == [] and e3["evidence_withheld"] == 1
    md = escalation_markdown(store.get_case("demo-003"))
    assert "Decision expected from support" in md and "withheld" in md and "SIMULATED" in md


def test_events_stored_per_session(client):
    ev = {"session_id": "s1", "type": "state_changed", "state": "running", "simulated": True}
    assert client.post("/events", json=ev).status_code == 401
    assert client.post("/events", json=ev, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 202
    bad = ev | {"state": "flying"}
    assert client.post("/events", json=bad, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 422
    assert client.get("/sessions/s1/events", auth=AUTH).json() == [ev]


def test_dashboard_escapes_and_flags(client):
    r = resolved_activity()
    r["goal"] = "<script>alert(1)</script>"
    post(client, r)
    html = client.get("/dashboard", auth=AUTH).text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "SIMULATED" in html and "DEMO" in html


def test_secrets_generated_when_missing():
    s = Settings()
    s.ensure_secrets()
    assert s.ingest_token and s.dashboard_password and len(s.generated_secrets) == 2


def test_billing_requires_test_key(client):
    assert client.get("/billing/plans").json()["configured"] is False
    r = client.post("/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 503 and "STRIPE_SECRET_KEY" in r.json()["detail"]
    assert client.post("/billing/checkout", json={"plan": "gold"}).status_code == 422


def test_billing_refuses_live_key_and_creates_test_session(monkeypatch):
    import hcs_backend.billing as billing

    calls = []

    class FakeSession:
        @staticmethod
        def create(**kw):
            calls.append(kw)
            return type("S", (), {"url": "https://checkout.stripe.com/c/pay/cs_test_123"})()

    monkeypatch.setattr(billing.stripe.checkout, "Session", FakeSession)
    live = TestClient(create_app(Settings(ingest_token=TOKEN, dashboard_password="pw", stripe_secret_key="sk_live_x"), Store(":memory:")))
    assert live.post("/billing/checkout", json={"plan": "pro"}).status_code == 503
    test = TestClient(create_app(Settings(ingest_token=TOKEN, dashboard_password="pw", stripe_secret_key="sk_test_x"), Store(":memory:")))
    r = test.post("/billing/checkout", json={"plan": "pro"}, headers={"Origin": "http://127.0.0.1:5173"})
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.com/")
    assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert calls[0]["mode"] == "subscription" and calls[0]["line_items"][0]["price_data"]["recurring"] == {"interval": "month"}
    test.post("/billing/checkout", json={"plan": "fixpack"})
    assert calls[1]["mode"] == "payment" and "recurring" not in calls[1]["line_items"][0]["price_data"]
