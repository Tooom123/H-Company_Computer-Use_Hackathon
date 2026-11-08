"""Benchmark plumbing: coordinates, hit test, and F = exactly the agent's grounding request."""

import importlib.util
import inspect
from pathlib import Path

from PIL import Image

spec = importlib.util.spec_from_file_location("run_bench", Path(__file__).with_name("run_bench.py"))
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)


def test_box_on_a_crop_maps_back_to_screen_pixels():
    crop = {"x": 600, "y": 300, "width": 500, "height": 400}
    assert rb.to_screen({"x1": 400, "y1": 400, "x2": 600, "y2": 600}, crop) == (850.0, 500.0)
    full = {"x": 0, "y": 0, "width": 1440, "height": 900}
    assert rb.to_screen({"x1": 0, "y1": 0, "x2": 1000, "y2": 1000}, full) == (720.0, 450.0)
    assert rb.to_screen({"x1": 1}, full) is None


def test_hit_uses_the_target_box():
    r = {"x": 100, "y": 100, "width": 50, "height": 20}
    assert rb.hit((125, 110), r) and rb.hit((151, 121), r)  # 2 px tolerance
    assert not rb.hit((160, 110), r) and not rb.hit(None, r)


def test_full_screen_request_is_the_agents_one():
    from hcs_agent.grounding import Grounder

    src = inspect.getsource(Grounder.locate)
    assert "Give the tight bounding box of that" in src and "Give the tight bounding box of that" in rb.prompt_for("x", False)
    assert rb.prompt_for("the New button", False).startswith("Locate: the New button.")
    assert rb.CROP_CONTEXT in rb.prompt_for("x", True) and "not_found" in rb.prompt_for("x", True)


def test_images_sent():
    screen = Image.new("RGB", (1440, 900), "white")
    assert rb.full_image(screen).size == (1024, 640)  # as grounding.capture()
    assert rb.crop_image(screen, {"x": 10, "y": 20, "width": 512, "height": 320}).size == (512, 320)
    assert rb.crop_image(screen, {"x": 0, "y": 0, "width": 1440, "height": 900}).width == 1024  # never bigger than F


def test_centre_crop_control_has_the_gaze_crop_size():
    c = rb.centre_crop({"x": 900, "y": 10, "width": 600, "height": 400}, 1440, 900)
    assert c == {"x": 420, "y": 250, "width": 600, "height": 400}


def test_mcnemar_and_wilson():
    assert rb.mcnemar(0, 0) == 1.0
    assert rb.mcnemar(0, 10) < 0.01
    lo, hi = rb.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60


def test_grow_crop_keeps_centre_and_stays_on_screen():
    assert rb.grow_crop({"x": 600, "y": 300, "width": 512, "height": 320}, 1440, 900, 768, 480) == {"x": 472, "y": 220, "width": 768, "height": 480}
    assert rb.grow_crop({"x": 1300, "y": 800, "width": 140, "height": 100}, 1440, 900, 768, 480) == {"x": 672, "y": 420, "width": 768, "height": 480}
    assert "zoomed" not in rb.prompt_for("x", True, context=False) and "not_found" in rb.prompt_for("x", True, context=False)
