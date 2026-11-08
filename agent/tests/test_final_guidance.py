"""Terminal guidance must be drawn even when no awaiting_user tick occurs."""

from types import SimpleNamespace

import pytest

from hcs_agent import cli
from hcs_agent.contract import CaseStatus, GuidanceStep, Mode, State


class Overlay:
    def __init__(self):
        self.hold_reveal = lambda: False
        self.scene = SimpleNamespace(target=(20, 30), text="Previous step")
        self.view = SimpleNamespace(scene=self.scene)
        self.scenes, self.waits = [], []

    def badge(self, *args, **kwargs):
        pass

    def hide(self):
        self.scene = None
        self.view.scene = None

    def show_scene(self, scene, animate=True):
        self.scene = scene
        self.view.scene = scene
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
    monkeypatch.setitem(cli._MAGNET, "current", None)
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
    assert overlay.scene.why == "I've checked this on screen."
    assert spoken == [(it.guidance[-1].instruction, "I've checked this on screen.")]
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
    assert overlay.scene.why == "I couldn't confirm the result yet."
    assert overlay.scene.doodle == "question"
    assert spoken[0] == (it.guidance[-1].instruction, "I couldn't confirm the result yet.")
    assert it.report.status is CaseStatus.escalated and it.report.verification.satisfied is False


@pytest.mark.parametrize("status,mode", [(CaseStatus.abandoned, Mode.guide), (CaseStatus.resolved, Mode.act)])
def test_stopped_or_act_case_does_not_reuse_a_stale_guide_target(rig, status, mode):
    overlay, spoken, _ = rig
    cli._show_outcome(overlay, intervention(status, mode=mode))
    assert getattr(overlay.scene, "target", None) is None
    assert "Read the Agent Answer panel." not in spoken[0]


def test_missing_verification_does_not_claim_a_support_handoff_or_success(rig):
    overlay, spoken, _ = rig
    it = intervention(CaseStatus.escalated, mode=Mode.act)
    cli._show_outcome(overlay, it)
    assert spoken == [("I couldn't confirm the result yet.", "This needs another look.")]
    assert it.report.verification.satisfied is False


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


def test_takeover_speaks_one_acknowledgement_not_internal_action_labels(rig, monkeypatch):
    ov, spoken, _ = rig
    it = intervention()
    it.state, it.report, it.takeover = State.running, None, True
    monkeypatch.setattr(cli, "_LAST_ACTION", {})
    monkeypatch.setattr(cli, "_voice_input_active", lambda: False)
    def run(done, tick, interval):
        for index, label in enumerate(("Preparing the response…", "Reading the screen…", "Selecting an on-screen control…")):
            cli._LAST_ACTION.update(id=str(index), summary=label, pointer=None)
            tick()
        it.state, it.report = State.resolved, object()
        assert done()
    ov.run_until = run
    cli._guide_loop(it, auto=False, overlay=True, ov=ov)
    assert spoken == [("Give me a moment, I'll check that.",)]
    assert ov.scenes == []  # no generic operational status presented as an explanatory note


def test_takeover_narrates_public_content_and_removes_only_stale_pointer(rig, monkeypatch):
    ov, spoken, clock = rig
    it = intervention()
    it.state, it.report, it.takeover = State.running, None, True
    it.request = SimpleNamespace(session_id="tour")
    monkeypatch.setattr(cli, "_LAST_ACTION", {})
    monkeypatch.setattr(cli, "_voice_input_active", lambda: False)
    def event(id, explanation, session="tour"):
        cli._print_event(SimpleNamespace(type="step", session_id=session, event_id=id,
            simulated=True, message=explanation, data={"step": {"kind": "action", "detail": {
                "tools": ["click_desktop"], "narration": explanation, "pointer": (80, 90)}}}))
    def run(done, tick, interval):
        event("old", "An obsolete instruction.", session="old-run")
        tick()
        assert not spoken and not ov.scenes
        event("one", "Projects organizes related work.")
        tick()
        assert ov.scene.target == (80, 90)
        clock[0] += 1
        cli._LAST_ACTION["stale_at"] = clock[0]
        tick()
        assert getattr(ov.scene, "target", None) is None
        assert ov.scene.text == "Projects organizes related work."
        event("duplicate", "Projects organizes related work.")
        tick()
        assert len(spoken) == 1
        event("two", "Sessions shows your agent runs and their results.")
        tick()
        event("late", "An obsolete instruction.", session="old-run")
        tick()
        assert ov.scene.text == "Sessions shows your agent runs and their results."
        it.state, it.report = State.resolved, object()
        assert done()
    ov.run_until = run
    cli._guide_loop(it, auto=False, overlay=True, ov=ov)
    assert spoken == [("Projects organizes related work.",), ("Sessions shows your agent runs and their results.",)]


def _tour_event(event_id, *, narration="", tools=None, observation=False, session="tour", attempt=1, **detail):
    cli._print_event(SimpleNamespace(type="step", session_id=session, event_id=event_id,
        simulated=True, message="", data={"step": {
            "kind": "observation" if observation else "action", "attempt": attempt,
            "detail": {"tools": tools, "narration": narration, **detail}}}))


def test_fast_observation_detaches_pointer_and_new_action_resets_freshness(rig, monkeypatch):
    ov, spoken, clock = rig
    it = intervention()
    it.state, it.report, it.takeover = State.running, None, True
    it.request = SimpleNamespace(session_id="tour")
    monkeypatch.setitem(cli._MAGNET, "current", it)
    monkeypatch.setattr(cli, "_LAST_ACTION", {})
    monkeypatch.setattr(cli, "_voice_input_active", lambda: False)

    def run(done, tick, interval):
        _tour_event("one", narration="Projects organize related work.", tools=["click_desktop"], pointer=(80, 90))
        tick()
        assert ov.scene.target == (80, 90)
        clock[0] += 0.05
        _tour_event("screen-one", observation=True)
        tick()
        assert getattr(ov.scene, "target", None) is None
        assert ov.scene.text == "Projects organize related work."

        _tour_event("two", narration="Sessions show the results.", tools=["click_desktop"], pointer=(180, 190))
        tick()
        assert ov.scene.target == (180, 190)
        assert cli._LAST_ACTION["stale_at"] is None
        _tour_event("late", narration="An obsolete instruction.", tools=["click_desktop"], session="old-run")
        _tour_event("old-screen", observation=True, session="old-run")
        tick()
        assert cli._LAST_ACTION["id"] == "two"
        assert cli._LAST_ACTION["stale_at"] is None
        assert ov.scene.target == (180, 190)

        # Even an observation at exactly the same clock time follows the action in the event stream.
        _tour_event("screen-two", observation=True)
        tick()
        assert getattr(ov.scene, "target", None) is None
        assert ov.scene.text == "Sessions show the results."
        it.state, it.report = State.resolved, object()
        assert done()

    ov.run_until = run
    cli._guide_loop(it, auto=False, overlay=True, ov=ov)
    assert spoken == [("Projects organize related work.",), ("Sessions show the results.",)]


def test_unnarrated_actions_detach_pointer_without_extending_explanation_lifetime(rig, monkeypatch):
    ov, spoken, clock = rig
    ov.reading_duration = 4
    it = intervention()
    it.state, it.report, it.takeover = State.running, None, True
    it.request = SimpleNamespace(session_id="tour")
    monkeypatch.setattr(cli, "_LAST_ACTION", {})
    monkeypatch.setattr(cli, "_voice_input_active", lambda: False)

    def run(done, tick, interval):
        _tour_event("one", narration="Projects organize related work.", tools=["click_desktop"], pointer=(80, 90))
        tick()
        assert ov.scene.target == (80, 90)
        clock[0] += 1
        _tour_event("wait-one", tools=["wait"])
        tick()
        assert getattr(ov.scene, "target", None) is None
        assert ov.scene.text == "Projects organize related work."
        clock[0] += 2
        _tour_event("wait-two", tools=["wait"])
        tick()
        assert ov.scene.text == "Projects organize related work."
        clock[0] += 1.1
        _tour_event("wait-three", tools=["wait"])
        tick()
        assert ov.scene is None  # expiry is measured from the explanation, not from each wait
        it.state, it.report = State.resolved, object()
        assert done()

    ov.run_until = run
    cli._guide_loop(it, auto=False, overlay=True, ov=ov)
    assert spoken == [("Projects organize related work.",)]


def test_tool_free_public_explanation_is_narrated_without_reasoning_fallback(rig, monkeypatch):
    ov, spoken, _ = rig
    it = intervention()
    it.state, it.report, it.takeover = State.running, None, True
    it.request = SimpleNamespace(session_id="tour")
    monkeypatch.setattr(cli, "_LAST_ACTION", {})
    monkeypatch.setattr(cli, "_voice_input_active", lambda: False)

    def run(done, tick, interval):
        _tour_event("private", reasoning="Private chain of thought.", arguments={"text": "Raw tool input."})
        tick()
        assert not spoken and not cli._LAST_ACTION
        _tour_event("explanation", narration="Sessions show your agent runs and their results.")
        tick()
        assert ov.scene.text == "Sessions show your agent runs and their results."
        assert getattr(ov.scene, "target", None) is None
        it.state, it.report = State.resolved, object()
        assert done()

    ov.run_until = run
    cli._guide_loop(it, auto=False, overlay=True, ov=ov)
    assert spoken == [("Sessions show your agent runs and their results.",)]


def test_presented_closing_survives_empty_answer_events_until_outcome(rig, monkeypatch):
    ov, spoken, _ = rig
    it = intervention()
    it.state, it.report, it.takeover = State.running, None, True
    it.request = SimpleNamespace(session_id="tour")
    monkeypatch.setattr(cli, "_LAST_ACTION", {})
    monkeypatch.setattr(cli, "_voice_input_active", lambda: False)
    closing = "What would you like to explore next?"

    def run(done, tick, interval):
        _tour_event("closing", narration=closing, final_narration=True)
        tick()
        assert it._presented_actor_answer == closing
        _tour_event("answer", tools=["answer"])
        tick()
        assert it._presented_actor_answer == closing
        assert spoken == [(closing,)]
        _tour_event("verifier", narration="I will audit all completed steps.", tools=["answer"],
                    final_narration=True, attempt=0)
        tick()
        assert it._presented_actor_answer == closing
        assert spoken == [(closing,)]  # verifier prose cannot become a second tour ending
        # A later attempt's new explanation invalidates this closing.
        _tour_event("new-attempt", narration="Let me check Projects.", tools=["click_desktop"])
        tick()
        assert not it._presented_actor_answer
        it.state, it.report = State.resolved, object()
        assert done()

    ov.run_until = run
    cli._guide_loop(it, auto=False, overlay=True, ov=ov)
