"""ACT's useful final explanation must reach the user without becoming proof."""

import sys
from types import SimpleNamespace

import pytest

from hcs_agent import cli
from hcs_agent.contract import CaseStatus, DeclaredResult, GuidanceStep, Mode


class Overlay:
    def __init__(self):
        self.scene = None
        self.scenes = []
        self.done = None

    def badge(self, *args, **kwargs):
        pass

    def show_scene(self, scene):
        self.scene = scene
        self.scenes.append(scene)

    def run_until(self, done, tick, interval):
        self.done = done

    def hide(self):
        self.scene = None


@pytest.fixture
def rig(monkeypatch):
    spoken, clock = [], [100.0]
    monkeypatch.setitem(sys.modules, "hcs_agent.overlay", SimpleNamespace(Scene=SimpleNamespace))
    monkeypatch.setattr(cli, "_say", lambda *segments, **kwargs: spoken.append(segments))
    monkeypatch.setattr(cli, "_new_request_pending", lambda: False)
    monkeypatch.setattr(cli.time, "time", lambda: clock[0])
    monkeypatch.setitem(cli._SPEECH, "speaker", None)
    return SimpleNamespace(overlay=Overlay(), spoken=spoken, clock=clock)


def intervention(summary, *, status=CaseStatus.resolved, outcome="done", mode=Mode.act):
    declared = DeclaredResult(outcome=outcome, summary=summary)
    report = SimpleNamespace(status=status, mode=mode, declared=declared, escalation=None,
                             verification=SimpleNamespace(satisfied=status is CaseStatus.resolved))
    # A previous guide target must not leak into the ACT answer.
    stale = GuidanceStep(index=1, instruction="Old instruction", pointer=(400, 500),
                         box=(380, 480, 40, 40), last=False)
    return SimpleNamespace(report=report, guidance=[stale], takeover=True)


def test_act_final_speaks_actual_explanation_with_separate_verified_status(rig):
    answer = "Projects organize related work. Agents define the assistant, while Sessions show its runs."
    it = intervention(answer)
    original = it.report.declared.model_dump()
    cli._show_outcome(rig.overlay, it)
    assert rig.overlay.scene.text == answer
    assert rig.overlay.scene.why == "I've checked this on screen."
    assert getattr(rig.overlay.scene, "target", None) is None
    assert getattr(rig.overlay.scene, "target_box", None) is None
    assert rig.spoken == [(answer, "I've checked this on screen.")]
    assert it.report.declared.model_dump() == original


def test_unverified_act_explanation_is_not_silently_promoted_to_verified(rig):
    answer = "Sessions lists your agent runs and their recorded outputs."
    it = intervention(answer, status=CaseStatus.escalated, outcome="unclear")
    original = it.report.declared.model_dump()
    cli._show_outcome(rig.overlay, it)
    assert rig.overlay.scene.text == answer
    assert rig.overlay.scene.why == "I couldn't confirm the result yet."
    assert rig.spoken == [(answer, "I couldn't confirm the result yet.")]
    assert it.report.status is CaseStatus.escalated
    assert it.report.verification.satisfied is False
    assert it.report.declared.model_dump() == original


def test_guide_that_took_over_uses_actor_answer_without_a_stale_guide_note(rig):
    answer = "Browser profiles retain a cloud browser's sign-in state."
    it = intervention(answer, mode=Mode.guide)
    cli._show_outcome(rig.overlay, it)
    assert rig.overlay.scene.text == answer
    assert "Old instruction" not in rig.spoken[0]
    assert getattr(rig.overlay.scene, "target", None) is None


@pytest.mark.parametrize("status,outcome", [
    (CaseStatus.abandoned, "done"),
    (CaseStatus.escalated, "not_run"),
])
def test_stopped_or_unexecuted_task_never_replays_stale_actor_summary(rig, status, outcome):
    it = intervention("Stale answer from before the interruption.", status=status, outcome=outcome)
    original = it.report.declared.model_dump()
    cli._show_outcome(rig.overlay, it)
    assert "Stale answer" not in rig.overlay.scene.text
    assert all("Stale answer" not in segment for speech in rig.spoken for segment in speech)
    assert it.report.declared.model_dump() == original


@pytest.mark.parametrize("raw", [
    '{"result": "done", "summary": "An internal fallback payload"}',
    'click_desktop({"x": 400, "y": 500})',
    "Preparing the response…",
])
def test_act_raw_code_or_internal_status_is_not_a_user_answer(rig, raw):
    it = intervention(raw)
    cli._show_outcome(rig.overlay, it)
    assert rig.overlay.scene.text == "I've checked this on screen."
    assert all(raw not in segment for speech in rig.spoken for segment in speech)
    assert it.report.declared.summary == raw  # original evidence remains available in its report


def test_act_final_waits_for_speech_but_remains_bounded_and_interruptible(rig, monkeypatch):
    speaker = SimpleNamespace(speaking=True)
    monkeypatch.setitem(cli._SPEECH, "speaker", speaker)
    cli._show_outcome(rig.overlay, intervention("Here's how the main sections fit together."))
    rig.clock[0] += 6
    assert not rig.overlay.done()  # five-second display timeout must not cut the spoken answer
    speaker.speaking = False
    assert rig.overlay.done()
    speaker.speaking = True
    monkeypatch.setattr(cli, "_new_request_pending", lambda: True)
    assert rig.overlay.done()
    monkeypatch.setattr(cli, "_new_request_pending", lambda: False)
    rig.clock[0] += 25
    assert rig.overlay.done()  # broken audio state cannot keep the completed task alive indefinitely
