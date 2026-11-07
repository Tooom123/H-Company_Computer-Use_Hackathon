from fastapi.testclient import TestClient

from hcs_agent.backend import MockBackend
from hcs_agent.server import create_app


def test_full_flow_over_http_and_ws(tmp_path):
    app = create_app(MockBackend(step_delay_s=0.01), tmp_path)
    with TestClient(app) as c:
        assert c.get("/health").json() == {"ok": True, "simulated": True}
        assert len(c.get("/procedures").json()) >= 2

        body = {"software": "odoo", "role": "new sales rep", "goal": "Follow up Acme Demo",
                "procedure_id": "odoo_crm_followup_activity",
                "parameters": {"opportunity": "Acme Demo", "due_date": "2026-11-14"}}
        created = c.post("/interventions", json=body).json()
        sid = created["session_id"]
        assert created["state"] == "awaiting_approval" and created["plan"]

        assert c.get(f"/interventions/{sid}/report").status_code == 425
        assert c.post(f"/interventions/{sid}/approve", json={"approved": True}).status_code == 200

        with c.websocket_connect(f"/interventions/{sid}/ws") as ws:
            types = []
            while True:
                e = ws.receive_json()
                types.append(e["type"])
                assert e["simulated"] is True
                if e["type"] == "finished":
                    break
        assert "plan_proposed" in types and "verification" in types and "step" in types

        report = c.get(f"/interventions/{sid}/report").json()
        assert report["status"] == "resolved" and report["verification"]["satisfied"] is True

        fb = c.post(f"/interventions/{sid}/feedback", json={"useful": True, "comment": "clear"}).json()
        assert fb["report_ready"]
        assert c.get(f"/interventions/{sid}/report").json()["feedback"]["comment"] == "clear"
        assert c.post(f"/interventions/{sid}/approve", json={"approved": True}).status_code == 409
