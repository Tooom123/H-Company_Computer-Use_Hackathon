"""Terminal guidance must be drawn even when no awaiting_user tick occurs."""

from types import SimpleNamespace

import pytest

from hcs_agent import cli
from hcs_agent.contract import CaseStatus, GuidanceStep, Mode, State


class Overlay:
    def __init__(self):
        self.hold_reveal = lambda: False
        self.scene = SimpleNamespace(target=(20, 30), text="Previous step")
        self.scenes, self.waits = [], []

    def badge(self, *args, **kwargs):
        pass

    def hide(self):
        self.scene = None

    def show_scene(self, scene):
        self.scene = scene
        self.scenes.append(scene)

    def run_until(self, done, tick, interval):
        self.waits.append(done)
        if tick is not None:
            # Reproduce a final answer that finished before the first UI tick.
            assert done()
            self.hide()


@pytest.fixture
def rig(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "hcs_agent.overlay", SimpleNamespace(Scene=SimpleNamespace))
    spoken, clock = [], [100.0]
    monkeypatch.setattr(cli, "_say", lambda *segments, **kwargs: spoken.append(segments))
    monkeypatch.setattr(cli, "_new_request_pending", lambda: False)
    monkeypatch.setattr(cli.time, "time", lambda: clock[0])
    monkeypatch.setitem(cli._SPEECH, "speaker", None)
    monkeypatch.setattr(cli, "_InputWatcher", lambda: SimpleNamespace(stop=lambda: None))
    return Overlay(), spoken, clock


def intervention(status=CaseStatus.resolved, *, pointer=(1057, 523), mode=Mode.guide):
    final = GuidanceStep(index=2, instruction="Read the Agent Answer panel.", where="Right panel",
                          pointer=pointer, box=(900, 300, 300, 400) if pointer else None, last=True)
    report = SimpleNamespace(status=status, mode=mode, escalation=None,
                             verification=SimpleNamespace(satisfied=status is CaseStatus.resolved))
    return SimpleNamespace(report=report, guidance=[final], state=State.resolved, _thread=None)


def test_final_only_answer_is_drawn_and_spoken_after_loop_exits_without_a_tick(rig):
    overlay, spoken, clock = rig
    it = intervention()
    cli._guide_loop(it, auto=False, overlay=True, ov=overlay)
    assert overlay.scenes == []  # last=True never entered awaiting_user
    cli._show_outcome(overlay, it)
    assert len(overlay.scenes) == 1
    assert overlay.scene.target == it.guidance[-1].pointer
    assert overlay.scene.target_box == it.guidance[-1].box
    assert overlay.scene.text == it.guidance[-1].instruction
    assert overlay.scene.why == "Done: result verified in the software"
    assert spoken == [("Done: result verified in the software", it.guidance[-1].instruction)]
    assert it.report.verification.satisfied is True
    assert overlay.waits[-1]() is False  # final note is not immediately hidden
    clock[0] += 6
    assert overlay.waits[-1]() is True


def test_unverified_final_guidance_is_visibly_and_audibly_qualified(rig):
    overlay, spoken, _ = rig
    it = intervention(CaseStatus.escalated)
    cli._show_outcome(overlay, it)
    assert overlay.scene.target == (1057, 523)
    assert overlay.scene.text == it.guidance[-1].instruction
    assert overlay.scene.why == "I could not verify the result"
    assert overlay.scene.doodle == "question"
    assert spoken[0] == ("I could not verify the result", it.guidance[-1].instruction)
    assert it.report.status is CaseStatus.escalated and it.report.verification.satisfied is False


@pytest.mark.parametrize("status,mode", [(CaseStatus.abandoned, Mode.guide), (CaseStatus.resolved, Mode.act)])
def test_stopped_or_act_case_does_not_reuse_a_stale_guide_target(rig, status, mode):
    overlay, spoken, _ = rig
    cli._show_outcome(overlay, intervention(status, mode=mode))
    assert getattr(overlay.scene, "target", None) is None
    assert "Read the Agent Answer panel." not in spoken[0]


def test_answer_without_target_keeps_its_explanation_without_inventing_a_marker(rig):
    overlay, _, _ = rig
    cli._show_outcome(overlay, intervention(pointer=None))
    assert overlay.scene.target is None
    assert overlay.scene.text == "Read the Agent Answer panel."


def test_final_note_survives_active_speech_but_new_request_has_priority(rig, monkeypatch):
    overlay, _, clock = rig
    speaker = SimpleNamespace(speaking=True)
    monkeypatch.setitem(cli._SPEECH, "speaker", speaker)
    cli._show_outcome(overlay, intervention())
    done = overlay.waits[-1]
    clock[0] += 6
    assert not done()
    speaker.speaking = False
    assert done()
    speaker.speaking = True
    clock[0] += 25
    assert done()  # bounded if a player incorrectly remains busy
    clock[0] = 100
    monkeypatch.setattr(cli, "_new_request_pending", lambda: True)
    assert done()


def test_paginated_answer_has_enough_reading_time_but_can_be_interrupted(rig, monkeypatch):
    overlay, _, clock = rig
    overlay.reading_duration = 24
    cli._show_outcome(overlay, intervention())
    done = overlay.waits[-1]
    clock[0] += 6
    assert not done()
    monkeypatch.setattr(cli, '_new_request_pending', lambda: True)
    assert done()
    monkeypatch.setattr(cli, '_new_request_pending', lambda: False)
    clock[0] += 20
    assert done()
