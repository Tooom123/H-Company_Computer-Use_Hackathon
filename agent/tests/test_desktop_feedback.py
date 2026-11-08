"""Human labels must not become model claims, and feedback dictation must not start a task."""

import argparse
import json
import threading
from types import SimpleNamespace

import pytest

from hcs_agent import cli
from hcs_agent.backend import MockBackend
from hcs_agent.contract import AgentEvent, InterventionRequest, Mode, State
from hcs_agent.control import Controller
from hcs_agent.desktop_feedback import DesktopFeedback, FeedbackError, RunJournal


def intervention(tmp_path, sid="sess_test", state=State.resolved):
    directory = tmp_path / sid
    directory.mkdir()
    it = SimpleNamespace(request=SimpleNamespace(session_id=sid), state=state,
                         report=SimpleNamespace(verification="unchanged"), runs_dir=directory,
                         backend=SimpleNamespace(simulated=True), received=[])
    it.add_feedback = it.received.append
    return it


def payload(sid="sess_test", **updates):
    return {"session_id": sid, "success": "partial", "useful": "unknown", "comment": "Presque",
            "confirmed_by_human": True, "allow_screenshots_to_support": False, "training_consent": False,
            **updates}


def test_explicit_labels_remain_separate_from_verification_and_never_train(tmp_path):
    it = intervention(tmp_path)
    fb = DesktopFeedback()
    fb.register(it)
    result = fb.save(payload())
    labels = json.loads((it.runs_dir / "labels.json").read_text())
    assert result["saved"] is True
    assert labels["label_source"] == "human" and labels["task_success_user"] == "partial"
    assert labels["user_confirmed"] and not labels["ready_for_sft"] and not labels["include_for_training"]
    assert not labels["allow_training"] and not labels["allow_screenshots_to_support"]
    assert it.received[0].useful is None and it.report.verification == "unchanged"
    with pytest.raises(FeedbackError, match="already saved"):
        fb.save(payload(success="yes"))
    assert json.loads((it.runs_dir / "labels.json").read_text())["success"] == "partial"


@pytest.mark.parametrize("updates", [
    {"confirmed_by_human": False}, {"confirmed_by_human": 1}, {"success": None}, {"useful": True},
    {"training_consent": True}, {"allow_screenshots_to_support": True}, {"comment": "x" * 4001},
    {"session_id": []}, {"session_id": "../escape"},
])
def test_invalid_feedback_cannot_write_labels(tmp_path, updates):
    it = intervention(tmp_path)
    fb = DesktopFeedback()
    fb.register(it)
    with pytest.raises(FeedbackError):
        fb.save(payload(**updates))
    assert not (it.runs_dir / "labels.json").exists() and not it.received


def test_dictated_draft_is_bound_to_finished_session_and_survives_new_question(tmp_path):
    fb = DesktopFeedback()
    first = intervention(tmp_path)
    fb.register(first)
    fb.arm({"session_id": "sess_test"})
    assert fb.consume_transcript("Continue, ce n'était pas utile.") is True
    assert fb.consume_transcript("A new question") is False
    assert not (first.runs_dir / "labels.json").exists()
    second = intervention(tmp_path, "sess_next", State.running)
    fb.register(second)
    assert fb.status()["comment"] == "Continue, ce n'était pas utile."
    assert fb.status()["session_id"] == "sess_test"
    with pytest.raises(FeedbackError, match="active task"):
        fb.arm({"session_id": "sess_test"})
    with pytest.raises(FeedbackError, match="finished"):
        fb.save(payload("sess_next"))
    assert json.loads((first.runs_dir / "feedback-draft.json").read_text())["confirmed_by_human"] is False
    second.state = State.resolved
    fb.save(payload(comment="Continue, ce n'était pas utile."))
    assert fb.status()["session_id"] == "sess_next"


def test_foreign_session_is_rejected(tmp_path):
    fb = DesktopFeedback()
    fb.register(intervention(tmp_path))
    with pytest.raises(FeedbackError, match="Unknown"):
        fb.arm({"session_id": "sess_foreign"})


def test_private_journal_preserves_request_and_concurrent_events(tmp_path):
    request = cli._hcompany_request("  Comment lire mes traces H ?  ")
    forwarded = []
    journal = RunJournal(tmp_path, request, forwarded.append)
    event = AgentEvent(session_id=request.session_id, type="state_changed", state=State.created)
    threads = [threading.Thread(target=journal, args=(event,)) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    saved = json.loads((journal.directory / "request.json").read_text())
    assert saved["goal"] == request.goal and saved["parameters"]["question"] == request.goal
    assert saved["mode"] == "guide" and saved["autonomy"] == 0
    assert len([json.loads(x) for x in (journal.directory / "events.jsonl").read_text().splitlines()]) == 12
    assert len(forwarded) == 12 and (journal.directory.stat().st_mode & 0o777) == 0o700
    journal(AgentEvent(session_id=request.session_id, type="state_changed", state=State.resolved))
    episode = json.loads((journal.directory / "episode.json").read_text())
    assert episode["scenario_id"] == "H-LIVE" and episode["state"] == "resolved" and episode["human_present"]
    assert episode["export_status"] == "pending" and episode["finished_at"]
    assert ((journal.directory / "request.json").stat().st_mode & 0o777) == 0o600
    with pytest.raises(FileExistsError):
        RunJournal(tmp_path, request, forwarded.append)
    bad = request.model_copy(update={"session_id": "../outside"})
    with pytest.raises(ValueError):
        RunJournal(tmp_path, bad, forwarded.append)


def test_control_feedback_and_observe_only_gate(tmp_path, monkeypatch):
    fb = DesktopFeedback()
    fb.register(intervention(tmp_path))
    levels = []
    ctl = Controller(tmp_path, status=dict, set_autonomy=levels.append, stop=lambda: False,
                     set_voice=dict, test_voice=lambda: False, feedback=fb)
    monkeypatch.setenv("HCS_GUIDE_OBSERVE_ONLY", "1")
    assert ctl.handle("POST", "/autonomy", {"level": 2})[0] == 403 and levels == []
    assert ctl.handle("POST", "/autonomy", {"level": 0})[0] == 200 and levels == [0]
    assert ctl.handle("GET", "/feedback", {})[1]["available"] is True
    assert ctl.handle("POST", "/feedback/dictate", {"session_id": "sess_test"})[1]["dictation_armed"]
    assert ctl.handle("POST", "/feedback", payload())[1]["saved"]
    assert ctl.handle("POST", "/feedback", payload())[0] == 409


def test_execute_journals_and_offers_finished_archive_hook_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_MAGNET", {"level": 2, "current": None, "widget": None})
    monkeypatch.setattr(cli, "_FEEDBACK", DesktopFeedback())
    monkeypatch.setattr(cli, "_print_event", lambda _: None)
    monkeypatch.delenv("HCS_GUIDE_OBSERVE_ONLY", raising=False)
    monkeypatch.delenv("HCS_BACKEND_URL", raising=False)
    finished = threading.Event()
    archived = []
    def hook(directory, report):
        archived.append((directory, report))
        finished.set()
    monkeypatch.setattr(cli, "_RUN_FINISHED_HOOK", hook)
    request = InterventionRequest(software="odoo", goal="Read the demo", mode=Mode.act,
                                  procedure_id="odoo_crm_followup_activity", parameters={"opportunity": "Demo"})
    assert cli._execute(request, MockBackend(step_delay_s=0.001), tmp_path, auto_approve=True, overlay=False) == 0
    assert finished.wait(1)
    directory, report = archived[0]
    assert directory == tmp_path / request.session_id and report["simulated"]
    assert (directory / "request.json").is_file() and (directory / "events.jsonl").is_file()
    assert json.loads((directory / "episode.json").read_text())["state"] == "resolved"


def test_hcompany_talk_bypasses_router_and_feedback_never_becomes_request(tmp_path, monkeypatch):
    from hcs_agent import voice
    fb = DesktopFeedback()
    fb.register(intervention(tmp_path))
    fb.arm({"session_id": "sess_test"})
    texts = iter(["Recommence, c'était peu utile", "Où est la durée de ma session H ?"])
    class PTT:
        key_name = "f9"
        def __init__(self, **kw):
            pass
        def start(self):
            pass
        def wait_transcript(self, **kw):
            return next(texts)
    monkeypatch.setattr(voice, "PushToTalk", PTT)
    monkeypatch.setattr(voice, "IntentRouter", lambda _: pytest.fail("Odoo router must not be constructed"))
    monkeypatch.setattr(cli, "_FEEDBACK", fb)
    monkeypatch.setattr(cli, "ProcedureRegistry", lambda: SimpleNamespace(get=lambda _: None))
    monkeypatch.setattr(cli, "make_backend", lambda _: SimpleNamespace())
    monkeypatch.setattr(cli, "_start_control", lambda *a: None)
    monkeypatch.setattr(cli, "_flash", lambda *a, **kw: None)
    requests = []
    monkeypatch.setattr(cli, "_execute", lambda req, *a, **kw: requests.append(req) or 0)
    args = argparse.Namespace(software="hcompany", no_overlay=True, mock=True, runs_dir=str(tmp_path),
                              key="f9", confirm=False, once=True)
    assert cli.cmd_talk(args) == 0
    assert len(requests) == 1 and requests[0].software == "h-company"
    assert requests[0].goal == "Où est la durée de ma session H ?"
    assert requests[0].mode is Mode.guide and requests[0].parameters["question"] == requests[0].goal
    assert fb.status()["comment"] == "Recommence, c'était peu utile"
