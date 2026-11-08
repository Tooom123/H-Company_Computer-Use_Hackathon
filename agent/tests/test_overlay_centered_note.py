"""Keep the reading position stable while the independently framed control changes."""

from dataclasses import replace
import sys
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Native AppKit layout/font metrics")


@pytest.fixture
def drawing(monkeypatch):
    from hcs_agent import overlay

    notes, frames, arrows = [], [], []
    monkeypatch.setattr(overlay, "_INSETS", {"left": 0, "right": 0, "top": 24, "bottom": 60})
    monkeypatch.setattr(overlay, "_ink", lambda: SimpleNamespace(setStroke=lambda: None))

    def note(x, y, text, rnd, *, size=19, max_w=480, **kwargs):
        _, _, w, h = overlay._measure(text, size, max_w)
        rect = (x - 10, y - 9, w + 20, h + 18)
        notes.append((text, rect))
        return rect

    monkeypatch.setattr(overlay, "_note", note)
    monkeypatch.setattr(overlay, "_frame", lambda x, y, rnd, style, **kw: frames.append((x, y, kw.get("box"))))
    monkeypatch.setattr(overlay, "_arrow", lambda a, b, rnd: arrows.append((a, b)))
    return SimpleNamespace(module=overlay, notes=notes, frames=frames, arrows=arrows)


@pytest.mark.parametrize("width,height", [(1470, 956), (800, 600), (600, 500)])
def test_note_and_explanation_do_not_jump_when_target_moves_or_disappears(drawing, width, height):
    ov = drawing.module
    view = ov._SketchView.alloc().initWithFrame_(((0, 0), (width, height)))
    scene = ov.Scene(text="Projects organize your workspace.", why="Each project keeps related work together.")
    baseline = None
    for target in (None, (80, height / 2), (width - 80, 100), (width / 2, height - 100), None):
        drawing.notes.clear()
        drawing.frames.clear()
        view.scene = replace(scene, target=target)
        view.drawRect_(view.bounds())
        rects = [rect for _, rect in drawing.notes]
        if baseline is None:
            baseline = rects
        assert rects == baseline  # including the pointer-free scene after invalidation
        for x, y, w, h in rects:
            assert x + w / 2 == pytest.approx(width / 2)
            assert 14 <= x and x + w <= width - 14
            assert 74 <= y and y + h <= height - 38
        assert drawing.frames == ([] if target is None else [(*target, None)])
        assert not drawing.arrows  # no cross-screen connector from the stable note


def test_control_box_and_explicit_annotation_arrow_are_preserved(drawing):
    ov = drawing.module
    view = ov._SketchView.alloc().initWithFrame_(((0, 0), (1470, 956)))
    box = (700, 400, 100, 40)
    view.scene = ov.Scene(text="This is where you start.", target=(750, 420), target_box=box,
                          marks=[ov.Mark("arrow", (100, 200), to=(200, 200))])
    view.drawRect_(view.bounds())
    assert drawing.frames == [(750, 420, box)]
    assert drawing.arrows == [((100, 200), (200, 200))]


def test_detaching_target_preserves_note_page_and_animation_state(monkeypatch):
    from hcs_agent import overlay

    monkeypatch.setattr(overlay, "_on_main", lambda fn: fn())
    ov = overlay.Overlay.__new__(overlay.Overlay)
    ov._screen_h, ov._seed, ov.hold_reveal = 956, 1, None
    ov.window = SimpleNamespace(orderFrontRegardless=lambda: None)
    ov.view = SimpleNamespace(scene=None,
        bounds=lambda: SimpleNamespace(size=SimpleNamespace(width=1470, height=956)),
        setNeedsDisplay_=lambda _: None)
    text = "Projects organize your workspace. " * 30
    scene = overlay.Scene(text=text, target=(100, 200))
    ov.show_scene(scene)
    assert len(ov.view.page_scenes) > 1
    ov.view.page_index, ov.view.page_started_at = 1, 42
    seed = ov.view.seed
    ov.show_scene(replace(scene, target=None), animate=False)
    assert ov.view.page_index == 1 and ov.view.page_started_at == 42
    assert ov.view.seed == seed and ov.view.progress == 1 and not ov.view.held
    assert all(page.target is None for page in ov.view.page_scenes)
    assert "".join(page.text for page in ov.view.page_scenes) == text
