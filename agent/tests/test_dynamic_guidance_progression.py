"""Dynamic GUIDE prepares audio but reobserves before offering another action. No H calls."""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from hcs_agent.backend import GuideAnswer, GuideSubStep, HBackend, _guidance_reply_message
from hcs_agent.contract import GuidanceStep, InterventionReport, InterventionRequest, Mode
from hcs_agent.knowledge import NoKnowledge
from hcs_agent.procedures import ProcedureRegistry


def _bound():
    req = InterventionRequest(software="h-company", goal="Explain the current session", mode=Mode.guide,
        procedure_id="hcompany_general_guide", parameters={"question": "Explain the current session"})
    return ProcedureRegistry().for_request(req).bound(req)


def _run(monkeypatch, answers, replies):
    backend = object.__new__(HBackend)
    backend.knowledge, backend.timezone_name = NoKnowledge(), "Europe/Paris"
    seen, messages, events, calls = [], [], [], []
    stop = threading.Event()
    handle = SimpleNamespace(id="offline-dynamic-guide",
        send_message=lambda message: (messages.append(message), events.append("send")),
        cancel=lambda: events.append("cancel"))
    backend._client = SimpleNamespace(start_session=lambda **kwargs: calls.append(kwargs) or handle)
    monkeypatch.setattr(backend, "_agent_spec", lambda name, instructions, **kwargs: {"instructions": instructions})
    monkeypatch.setattr(backend, "_watch_stop", lambda *args: None)
    monkeypatch.setattr(backend, "locate", lambda *args: pytest.fail("Unexpected grounding request"))
    turns, responses = iter(answers), iter(replies)

    def turn(*args):
        events.append("observe")
        return SimpleNamespace(answer=next(turns), status="idle", events=[]), len(events), len(events)

    def guidance(step):
        events.append(f"show:{step.instruction}")
        seen.append(step)
        return None if step.last else next(responses)

    monkeypatch.setattr(backend, "_turn", turn)
    result = backend.run_guidance(_bound(), "Explain", lambda step: None, guidance, stop)
    return result, seen, messages, events, calls


def test_batch_candidates_only_prefetch_and_new_observation_replaces_stale_step(monkeypatch):
    first = GuideAnswer(steps=[
        GuideSubStep(instruction="Open the session", done_when="Session details are visible"),
        GuideSubStep(instruction="Read the old field", why="Do not concatenate this into the audio key"),
        GuideSubStep(instruction="Open its old menu"),
        GuideSubStep(instruction="An excessive candidate is ignored"),
    ])
    second = GuideAnswer(instruction="Read the new panel", kind="info",
        done_when="The session status is visible")
    final = GuideAnswer(instruction="The status is visible", kind="info", last=True)
    result, seen, messages, events, calls = _run(monkeypatch, [first, second, final], [
        (True, "Observed interaction: click inside target. Result not verified."), (True, None)])

    assert result.error is None
    assert [s.instruction for s in seen] == ["Open the session", "Read the new panel", "The status is visible"]
    assert seen[0].prepared_speech == ["Read the old field", "Open its old menu"]
    assert seen[1].prepared_speech == [] and seen[1].kind == "info"
    assert seen[0].done_when == "Session details are visible"
    assert seen[1].done_when == "The session status is visible"
    assert events == ["observe", "show:Open the session", "send", "observe", "show:Read the new panel",
                      "send", "observe", "show:The status is visible", "cancel"]
    assert len(calls) == 1  # same session, no separate speculative H/grounding request
    assert "fresh screenshot" in messages[0] and "Session details are visible" in messages[0]
    assert "I did it" not in messages[0] and "User reported" not in messages[0]
    assert "NOT human feedback" in calls[0]["agent"]["instructions"]


@pytest.mark.parametrize("last,blocked", [(True, False), (False, True)])
def test_terminal_answers_never_prepare_or_show_following_actions(monkeypatch, last, blocked):
    answer = GuideAnswer(last=last, blocked=blocked, instruction="Current explanation", steps=[
        GuideSubStep(instruction="Current explanation", kind="info"),
        GuideSubStep(instruction="Must not prepare a later action")])
    result, seen, messages, events, _ = _run(monkeypatch, [answer], [])
    assert result.error is None and seen[0].last
    assert seen[0].prepared_speech == [] and len(seen) == 1
    assert messages == []
    assert result.declared.outcome == ("blocked" if blocked else "done")


def test_aborted_step_does_not_send_confirmation_or_offer_prepared_step(monkeypatch):
    answer = GuideAnswer(steps=[GuideSubStep(instruction="Current action"),
                               GuideSubStep(instruction="Tentative later action")])
    result, seen, messages, events, _ = _run(monkeypatch, [answer], [None])
    assert result.error is None
    assert [s.instruction for s in seen] == ["Current action"]
    assert result.declared.outcome == "not_run" and messages == []


def test_reported_failure_reobserves_instead_of_continuing_batch(monkeypatch):
    answer = GuideAnswer(steps=[GuideSubStep(instruction="Open details"), GuideSubStep(instruction="Read details")])
    blocked = GuideAnswer(instruction="Permission is missing", last=True, blocked=True, blocker="Access denied")
    result, seen, messages, _, _ = _run(monkeypatch, [answer, blocked], [(False, "Access denied")])
    assert result.declared.outcome == "blocked"
    assert [s.instruction for s in seen] == ["Open details", "Permission is missing"]
    assert "User reported difficulty" in messages[0] and "Access denied" in messages[0]
    assert "not a verified outcome" in messages[0]


@pytest.mark.parametrize("kind", ["click", "type", "key", "info", "wait"])
def test_top_level_fallback_carries_interaction_kind_and_expected_result(monkeypatch, kind):
    answer = GuideAnswer(instruction="Current instruction", kind=kind, done_when="Expected visible state")
    _, seen, _, _, _ = _run(monkeypatch, [answer], [None])
    assert seen[0].kind == kind and seen[0].done_when == "Expected visible state"
    assert seen[0].prepared_speech == []


@pytest.mark.parametrize("done,note,expected_prefix", [
    (True, None, "User reported completing"),
    (False, "I cannot see it", "User reported difficulty"),
    (True, "Observed interaction: screen changed. Result not verified.", "Observed interaction:"),
    (True, "Observed interaction: wait elapsed. Result not verified.", "Observed interaction:"),
])
def test_signal_provenance_never_becomes_verified_success(done, note, expected_prefix):
    message = _guidance_reply_message(done, note, "The details panel is visible")
    assert message.startswith(expected_prefix)
    assert "I did it" not in message and "not a verified outcome" in message
    assert "fresh screenshot" in message and "The details panel is visible" in message
    assert "discard any stale" in message


def test_new_contract_is_backwards_compatible_and_bounds_speculation():
    old = GuidanceStep(index=1, instruction="Read the page")
    assert old.prepared_speech == [] and old.done_when is None
    new = GuidanceStep(index=2, instruction="Read the panel", prepared_speech=["Next", "Later"])
    assert GuidanceStep.model_validate_json(new.model_dump_json()) == new
    with pytest.raises(ValidationError):
        GuidanceStep(index=3, instruction="Current", prepared_speech=["One", "Two", "Three"])
    with pytest.raises(ValidationError):
        GuideAnswer(instruction="No arbitrary autonomous action", kind="execute_shell")


@pytest.mark.parametrize("model", [GuidanceStep, InterventionReport])
def test_published_schema_accepts_the_current_guidance_contract(model):
    path = Path(__file__).resolve().parents[2] / "contracts" / f"{model.__name__}.schema.json"
    assert json.loads(path.read_text()) == model.model_json_schema()
