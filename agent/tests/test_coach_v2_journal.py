"""The clean coach journals evidence, never invents successful or human labels."""

import json
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from hcs_agent.coach_v2_journal import CoachRun
from hcs_agent.contract import FeedbackCommand
from hcs_agent.control import read_reports
from hcs_agent.desktop_feedback import DesktopFeedback, FeedbackError


def human_labels(run):
    return {"session_id": run.session_id, "success": "partial", "useful": "yes",
            "comment": "Useful, but I had to find the last button myself.",
            "confirmed_by_human": True, "allow_screenshots_to_support": False,
            "training_consent": False}


def test_runs_are_distinct_private_and_keep_model_claim_unverified(tmp_path):
    root = tmp_path / "private-runs"
    run = CoachRun(root, "Where are my sessions?", "guide")
    other = CoachRun(root, "Where are my sessions?", "guide")
    assert run.session_id != other.session_id
    run.record("observation", {"url": "https://platform.hcompany.ai/agents/sessions"})
    run.record("model_response", {"speech": "Your sessions are here.", "usage": {"input_tokens": 120}})
    report = run.finish("done", "Your sessions are here.")
    assert report["declared"]["outcome"] == "done"
    assert report["verification"] == {
        "performed": False, "satisfied": False,
        "observed": "No independent task verification was performed.",
    }
    assert report["feedback"] is None
    assert not (run.runs_dir / "labels.json").exists()
    summaries = read_reports(root)
    assert len(summaries) == 1
    assert summaries[0]["verified"] is False and summaries[0]["useful"] is None
    assert summaries[0]["goal"] == run.request.goal and summaries[0]["duration_s"] >= 0
    assert summaries[0]["cost_usd"] is None and summaries[0]["simulated"] is False
    for directory in [root, run.runs_dir, other.runs_dir]:
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for path in run.runs_dir.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_concurrent_events_are_complete_and_ordered(tmp_path):
    run = CoachRun(tmp_path / "runs", "Read a session", "guide")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: run.record("observation", {"index": i}), range(60)))
    entries = [json.loads(line) for line in (run.runs_dir / "events.jsonl").read_text().splitlines()]
    assert len(entries) == 61
    assert [entry["sequence"] for entry in entries] == list(range(1, 62))
    assert {entry["payload"]["index"] for entry in entries[1:]} == set(range(60))
    assert all(entry["simulated"] is False for entry in entries)


def test_finish_is_immutable_and_late_wait_does_not_reopen_run(tmp_path):
    run = CoachRun(tmp_path / "runs", "Read a session", "act")
    run.set_waiting()
    assert run.state.value == "awaiting_user" and not run.state.terminal
    run.set_running()
    assert run.state.value == "running"
    first = run.finish("interrupted", "Stopped.")
    run.finish("done", "A stale model response.")
    run.set_waiting()
    assert run.state.terminal and run.state.value == "stopped"
    assert run.report == first and run.report["declared"]["summary"] == "Stopped."
    saved = json.loads((run.runs_dir / "report.json").read_text())
    assert saved["status"] == "stopped" and saved["declared"]["outcome"] == "unclear"


def test_existing_desktop_feedback_is_the_human_label_gate(tmp_path):
    root = tmp_path / "runs"
    run = CoachRun(root, "Show me my sessions", "guide")
    feedback = DesktopFeedback()
    feedback.register(run)
    with pytest.raises(FeedbackError, match="finished"):
        feedback.save(human_labels(run))
    run.finish("done", "Your sessions are here.")
    with pytest.raises(ValueError, match="DesktopFeedback"):
        run.add_feedback(FeedbackCommand(useful=True))
    feedback.arm({"session_id": run.session_id})
    assert feedback.consume_transcript("A voice comment")
    assert not (run.runs_dir / "labels.json").exists()
    assert feedback.save(human_labels(run))["saved"]
    labels = json.loads((run.runs_dir / "labels.json").read_text())
    report = json.loads((run.runs_dir / "report.json").read_text())
    assert labels["label_source"] == "human" and labels["task_success_user"] == "partial"
    assert not labels["ready_for_sft"] and not labels["training_consent"]
    assert report["feedback"]["useful"] is True
    assert report["verification"]["satisfied"] is False
    assert read_reports(root)[0]["verified"] is False
    with pytest.raises(FeedbackError, match="already saved"):
        feedback.save(human_labels(run))
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in run.runs_dir.iterdir())


def test_journal_does_not_follow_a_replaced_event_file(tmp_path):
    run = CoachRun(tmp_path / "runs", "Read a session", "guide")
    outside = tmp_path / "outside.txt"
    outside.write_text("untouched")
    path = run.runs_dir / "events.jsonl"
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(OSError):
        run.record("observation", {})
    assert outside.read_text() == "untouched"


def test_invalid_payload_does_not_append_broken_json(tmp_path):
    run = CoachRun(tmp_path / "runs", "Read a session", "guide")
    with pytest.raises(ValueError):
        run.record("usage", {"latency": float("nan")})
    run.record("usage", {"latency": 0.2})
    entries = [json.loads(line) for line in (run.runs_dir / "events.jsonl").read_text().splitlines()]
    assert [entry["sequence"] for entry in entries] == [1, 2]
