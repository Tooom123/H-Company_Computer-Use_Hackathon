"""Auto-fix with Devin: allowlist, auto trigger on suspected defects, manual trigger, polling, dashboard."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from hcs_backend.app import create_app
from hcs_backend.autofix import AutoFixer, MockProvider, build_prompt, parse_repo_map
from hcs_backend.config import Settings
from hcs_backend.demo import defect_due_date, resolved_activity
from hcs_backend.store import Store

TOKEN, AUTH = "t", ("support", "pw")
REPO = "Tooom123/hcs-sandbox-fake-crm"


def make(auto=True, run_s=0.0):
    settings = Settings(ingest_token=TOKEN, dashboard_password="pw", fix_repos=f"Fake CRM={REPO}", fix_auto=auto)
    store = Store(":memory:")
    fixer = AutoFixer(settings, store, provider=MockProvider(run_s=run_s))
    return TestClient(create_app(settings, store, fixer=fixer, start_poller=False)), fixer


def post(client, report):
    return client.post("/cases", json=report, headers={"Authorization": f"Bearer {TOKEN}"})


def wait_fix(client, case_id, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/cases/{case_id}/fix", auth=AUTH)
        if r.status_code == 200:
            return r.json()
        time.sleep(0.02)
    raise AssertionError("no fix")


def test_repo_map_parsing():
    assert parse_repo_map("Fake CRM=a/b; Odoo CRM = c/d ;bad") == {"fake crm": "a/b", "odoo crm": "c/d"}


def test_suspected_defect_on_allowlisted_repo_triggers_devin_and_gets_a_pr():
    client, fixer = make(run_s=0.0)
    r = post(client, defect_due_date())
    assert r.status_code == 201 and r.json()["fix_requested"] is True
    fix = wait_fix(client, "demo-005")
    assert fix["repo"] == REPO and fix["branch"] == "feature/hcs-fix-demo-005" and fix["trigger"] == "auto"
    assert fix["simulated"] is True
    fix = client.get("/cases/demo-005/fix", auth=AUTH).json()  # refresh -> mock session finished
    assert fix["status"] == "exit" and fix["pr_url"].startswith(f"https://github.com/{REPO}/pull/")
    assert fixer.poll_open() == 0  # nothing left open
    html = client.get("/dashboard/cases/demo-005", auth=AUTH).text
    assert "Fix with Devin" in html and "pull/0" in html


def test_no_auto_fix_outside_defects_or_allowlist():
    client, _ = make()
    assert post(client, resolved_activity()).json()["fix_requested"] is False  # Odoo, usage: not eligible
    other = defect_due_date("demo-006")
    other["software"] = "Some Real Product"
    assert post(client, other).json()["fix_requested"] is False  # not on the allowlist
    assert client.post("/cases/demo-006/fix", auth=AUTH).status_code == 422


def test_auto_off_means_manual_only_and_one_fix_per_case():
    client, _ = make(auto=False)
    assert post(client, defect_due_date()).json()["fix_requested"] is False
    html = client.get("/dashboard/cases/demo-005", auth=AUTH).text
    assert "Send to Devin" in html
    r = client.post("/dashboard/cases/demo-005/fix", auth=AUTH, follow_redirects=False)
    assert r.status_code == 303
    first = client.post("/cases/demo-005/fix", auth=AUTH).json()
    again = client.post("/cases/demo-005/fix", auth=AUTH).json()
    assert first["session_id"] == again["session_id"] and first["trigger"] == "manual"


def test_fix_endpoints_require_support_auth():
    client, _ = make()
    post(client, defect_due_date())
    assert client.post("/cases/demo-005/fix").status_code == 401
    assert client.get("/fixes").status_code == 401


def test_prompt_is_a_usable_bug_brief():
    store = Store(":memory:")
    case, _ = store.add_case(defect_due_date())
    p = build_prompt(case, REPO)
    for needle in ("https://github.com/" + REPO, "feature/hcs-fix-demo-005", "2026-11-13", "test that fails",
                   "do not open a pull request", "Europe/Paris"):
        assert needle in p, needle


def test_devin_provider_payload(monkeypatch):
    import json
    from hcs_backend import autofix

    sent = {}

    class Resp:
        status = 200
        def __init__(self, body): self.body = body
        def read(self): return json.dumps(self.body).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout):
        sent["url"], sent["method"], sent["auth"] = req.full_url, req.get_method(), req.headers["Authorization"]
        sent["body"] = json.loads(req.data) if req.data else None
        if req.get_method() == "POST":
            return Resp({"session_id": "devin-abc", "url": "https://app.devin.ai/sessions/abc", "status": "new"})
        return Resp({"session_id": "devin-abc", "status": "exit",
                     "pull_requests": [{"pr_url": f"https://github.com/{REPO}/pull/7", "pr_state": "open"}]})

    monkeypatch.setattr(autofix.urllib.request, "urlopen", fake_urlopen)
    p = autofix.DevinProvider("cog_x", "org-1", max_acu=3)
    s = p.create(prompt="fix it", repo=REPO, title="t", tags=["h-companion"])
    assert sent["url"] == "https://api.devin.ai/v3/organizations/org-1/sessions" and sent["method"] == "POST"
    assert sent["auth"] == "Bearer cog_x" and sent["body"]["repos"] == [REPO] and sent["body"]["max_acu_limit"] == 3
    assert "structured_output_schema" in sent["body"] and s["session_id"] == "devin-abc"
    g = p.get("devin-abc")
    assert sent["url"].endswith("/sessions/devin-abc") and g["pull_requests"][0]["pr_url"].endswith("/pull/7")


def test_devin_waiting_for_user_is_shown_and_support_can_reply():
    class Waiting(MockProvider):
        def get(self, session_id):
            return {"session_id": session_id, "status": "running", "status_detail": "waiting_for_user", "pull_requests": []}

        def messages(self, session_id):
            return [{"source": "devin", "message": "On it."},
                    {"source": "devin", "message": "Blocked: I can't access the repo."}] + super().messages(session_id)

    settings = Settings(ingest_token=TOKEN, dashboard_password="pw", fix_repos=f"Fake CRM={REPO}", fix_auto=False)
    store = Store(":memory:")
    provider = Waiting(run_s=0)
    client = TestClient(create_app(settings, store, fixer=AutoFixer(settings, store, provider=provider), start_poller=False))
    post(client, defect_due_date())
    client.post("/cases/demo-005/fix", auth=AUTH)
    html = client.get("/dashboard/cases/demo-005", auth=AUTH).text
    assert "Devin is waiting for you" in html and "can&#x27;t access the repo" in html
    assert client.post("/cases/demo-005/fix/message", json={"message": ""}, auth=AUTH).status_code == 422
    r = client.post("/dashboard/cases/demo-005/fix/message", data={"message": "Access granted, please retry"},
                    auth=AUTH, follow_redirects=False)
    assert r.status_code == 303
    sid = store.get_fix("demo-005")["session_id"]
    assert provider.messages(sid)[-1] == {"source": "user", "message": "Access granted, please retry"}
    assert store.get_fix("demo-005")["replies"] == ["Access granted, please retry"]
