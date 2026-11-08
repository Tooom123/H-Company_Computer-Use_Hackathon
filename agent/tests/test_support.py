"""Support uplink: reports and events reach the support backend; nothing breaks when it is off or down."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from hcs_agent.backend import MockBackend
from hcs_agent.contract import ApproveCommand, FeedbackCommand, InterventionRequest
from hcs_agent.procedures import ProcedureRegistry
from hcs_agent.runner import Intervention
from hcs_agent.support import SupportUplink


class _Backend:
    """Tiny stand-in for hcs-backend: records what it receives."""

    def __init__(self, status: int = 201):
        received, status_ = [], status

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((self.path, self.headers.get("Authorization"), self.headers.get("X-HCS-User"), body))
                self.send_response(status_)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.received = received
        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


def _run(tmp_path, uplink):
    req = InterventionRequest(software="odoo", role="new sales rep", goal="Help me follow up Acme Demo",
                              procedure_id="odoo_crm_followup_activity",
                              parameters={"opportunity": "Acme Demo", "due_date": "2026-11-14"})
    it = Intervention(req, MockBackend(step_delay_s=0.01), ProcedureRegistry(), lambda e: None, tmp_path, uplink=uplink)
    it.start()
    it.approve(ApproveCommand(approved=True))
    it.wait(10)
    return it


def test_report_and_events_reach_the_backend(tmp_path):
    be = _Backend()
    up = SupportUplink(be.url, "tok", user_ref="demo-user-1")
    it = _run(tmp_path, up)
    assert up.flush(5)
    cases = [r for r in be.received if r[0] == "/cases"]
    events = [r for r in be.received if r[0] == "/events"]
    assert len(cases) == 1 and cases[0][1] == "Bearer tok" and cases[0][2] == "demo-user-1"
    assert cases[0][3]["case_id"] == it.report.case_id and cases[0][3]["simulated"] is True
    assert events and events[-1][3]["type"] == "finished" and events[0][2] is None  # user ref on cases only
    # feedback later: the same case is sent again (the backend replaces it)
    it.add_feedback(FeedbackCommand(useful=True, comment="clear"))
    assert up.flush(5)
    cases = [r for r in be.received if r[0] == "/cases"]
    assert len(cases) == 2 and cases[1][3]["feedback"]["comment"] == "clear"


def test_backend_down_does_not_break_the_run(tmp_path):
    up = SupportUplink("http://127.0.0.1:9", "tok", timeout_s=0.3, retries=0)
    it = _run(tmp_path, up)
    assert up.flush(5)
    assert it.report.status.value == "resolved" and up.failed >= 1
    assert (it.runs_dir / "report.json").exists()


def test_rejected_payload_is_not_retried(tmp_path):
    be = _Backend(status=422)
    up = SupportUplink(be.url, "tok", send_events=False, retries=2)
    _run(tmp_path, up)
    assert up.flush(5)
    assert len(be.received) == 1 and up.failed == 1


def test_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("HCS_BACKEND_URL", raising=False)
    assert SupportUplink.from_env() is None
    it = _run(tmp_path, False)
    assert it.uplink is None and it.report is not None
