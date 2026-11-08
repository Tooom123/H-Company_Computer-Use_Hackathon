"""Explicit GUIDE coordinate frame; no screenshots, model calls or native input."""

import sys
import threading
from types import SimpleNamespace

import pytest

from hcs_agent.backend import GuideAnswer, GuideSubStep, HBackend, _guide_target_to_screen, _lenient
from hcs_agent.contract import InterventionRequest, Mode
from hcs_agent.knowledge import NoKnowledge
from hcs_agent.procedures import ProcedureRegistry


def test_normalized_axes_use_logical_width_and_height_independently():
    size = (1470.0, 956.0)
    assert _guide_target_to_screen(500, 500, "normalized_1000", screen_size=size) == (735, 478)
    # Previously interpreted as pixels in a 1024x666 image -> y1274 / y1055.
    # These values are usable ONLY with the newly explicit normalized marker.
    assert _guide_target_to_screen(624, 888, "normalized_1000", screen_size=size) == (917, 849)
    assert _guide_target_to_screen(340, 735, "normalized_1000", screen_size=size) == (500, 703)
    assert _guide_target_to_screen(0, 0, "normalized_1000", screen_size=size) == (0, 0)
    assert _guide_target_to_screen(1000, 1000, "normalized_1000", screen_size=size) == (1469, 955)
    assert _guide_target_to_screen(250, 750, "normalized_1000", screen_size=(800, 600)) == (200, 450)


@pytest.mark.parametrize("frame", [None, "", "pixels", "screenshot_pixels", "normalized_1", "normalized_100"])
def test_missing_or_other_frame_is_never_inferred_from_values(frame):
    assert _guide_target_to_screen(624, 888, frame, screen_size=(1470, 956)) is None
    assert _guide_target_to_screen(.5, .5, frame, screen_size=(1470, 956)) is None


@pytest.mark.parametrize("bad", [None, True, False, "500", -1, 1001, float("nan"), float("inf"), -float("inf"), {}, [],
                                pytest.param(10 ** 1000, id="oversized-integer")])
def test_invalid_coordinates_hide_pointer_without_discarding_instruction(bad):
    for axis in ("target_x", "target_y"):
        data = {"instruction": "Read this label", "coordinate_system": "normalized_1000",
                "target_x": 500, "target_y": 500, axis: bad}
        answer = _lenient(GuideAnswer, data)
        assert answer is not None and answer.instruction == "Read this label"
        assert getattr(answer, axis) is None
        assert _guide_target_to_screen(answer.target_x, answer.target_y, answer.coordinate_system,
                                       screen_size=(1470, 956)) is None


@pytest.mark.parametrize("bad_size", [(0, 956), (1470, 0), (True, 956), (float("nan"), 956),
                                      (1470, float("inf")), (1470,), "screen"])
def test_unknown_geometry_never_falls_back_to_raw_pixels(bad_size):
    assert _guide_target_to_screen(500, 500, "normalized_1000", screen_size=bad_size) is None


def test_schema_and_instructions_define_the_same_coordinate_contract():
    schema = GuideAnswer.model_json_schema()
    assert schema["properties"]["coordinate_system"]["anyOf"][0]["const"] == "normalized_1000"
    for axis in ("target_x", "target_y"):
        numeric = schema["properties"][axis]["anyOf"][0]
        assert numeric["minimum"] == 0 and numeric["maximum"] == 1000
        assert "FULL screenshot" in schema["properties"][axis]["description"]
    answer = GuideAnswer(instruction="Keep this explanation", target_x=624, target_y=888)
    assert answer.coordinate_system is None  # older unmarked response: no guessing
    assert _guide_target_to_screen(answer.target_x, answer.target_y, answer.coordinate_system) is None
    step = GuideSubStep(instruction="Keep this step", target_x=-1, target_y=888)
    assert step.target_x is None and step.instruction == "Keep this step"


def _bound():
    request = InterventionRequest(software="h-company", goal="Explain this page", mode=Mode.guide,
                                  procedure_id="hcompany_general_guide", parameters={"question": "Explain this page"})
    return ProcedureRegistry().for_request(request).bound(request)


@pytest.mark.parametrize("frame,expected", [("normalized_1000", (917, 849)), (None, None), ("pixels", None)])
def test_dynamic_backend_uses_explicit_contract_without_a_second_model_call(monkeypatch, frame, expected):
    backend = object.__new__(HBackend)
    backend.knowledge, backend.timezone_name = NoKnowledge(), "Europe/Paris"
    backend.screenshot_max_width = 1280
    handle = SimpleNamespace(id="offline-fixture", cancel=lambda: None)
    calls = []
    backend._client = SimpleNamespace(start_session=lambda **kwargs: calls.append(kwargs) or handle)
    monkeypatch.setattr(backend, "_agent_spec", lambda name, instructions, **kwargs: {"instructions": instructions})
    monkeypatch.setattr(backend, "_watch_stop", lambda *args: None)
    monkeypatch.setattr(backend, "locate", lambda *args: pytest.fail("Unexpected extra grounding/model call"))
    monkeypatch.setitem(sys.modules, "hcs_agent.overlay", SimpleNamespace(screen_size_points=lambda: (1470, 956)))
    answer = GuideAnswer(instruction="Read this label", coordinate_system=frame, target_x=624, target_y=888, last=True)
    result = SimpleNamespace(answer=answer, status="idle", events=[])
    monkeypatch.setattr(backend, "_turn", lambda *args: (result, 1, 1))
    seen = []
    run = backend.run_guidance(_bound(), "Explain", lambda step: None, seen.append, threading.Event())
    assert len(calls) == 1 and len(seen) == 1 and run.error is None
    assert seen[0].pointer == expected
    instructions = calls[0]["agent"]["instructions"]
    assert '"normalized_1000"' in instructions
    assert "pixel position of the control" not in instructions
    assert "do not direct the user to confirm that mutation" in instructions
    assert "action forbidden" in instructions and "by asking the user to do it" in instructions
    assert "User question, verbatim" in instructions


def test_steps_share_top_level_coordinate_system(monkeypatch):
    # The schema defines a single frame for every returned substep.
    answer = GuideAnswer.model_validate({"instruction": "Read the left field", "coordinate_system": "normalized_1000",
        "steps": [{"instruction": "Read the left field", "target_x": 250, "target_y": 500},
                  {"instruction": "Read the right field", "target_x": 750, "target_y": 500}]})
    assert [_guide_target_to_screen(step.target_x, step.target_y, answer.coordinate_system, screen_size=(1470, 956))
            for step in answer.steps] == [(368, 478), (1102, 478)]
