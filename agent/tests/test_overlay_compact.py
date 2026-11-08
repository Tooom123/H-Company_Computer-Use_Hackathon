"""Folding the HUD must release its old input region and preserve active status visibility."""

from types import SimpleNamespace
import sys

import pytest

from hcs_agent.overlay_layout import is_idle_badge, magnet_hit, magnet_rect, magnet_size, shortcut_label


@pytest.mark.skipif(sys.platform != "darwin", reason="Native AppKit binding")
def test_compact_hit_region_does_not_leave_old_rail_blocked(monkeypatch):
    from hcs_agent import overlay
    frames, callbacks = [], []
    widget = overlay.MagnetWidget.__new__(overlay.MagnetWidget)
    widget.visible, widget.compact, widget._screen_h = True, False, 956
    widget.on_compact_changed = callbacks.append
    widget.window = SimpleNamespace(setFrame_display_=lambda frame, _: frames.append(frame))
    widget.view = SimpleNamespace(level=0, compact=False, setFrame_=lambda _: None, setNeedsDisplay_=lambda _: None)
    widget.rect = magnet_rect(956, False)
    monkeypatch.setattr(overlay, "_on_main", lambda fn: fn())
    assert widget.contains(320, 910)
    widget.set_compact(True)
    assert not widget.contains(320, 910)  # the old slider's right part is available to the underlying app
    assert widget.contains(40, 920)  # the explicit restore handle remains available
    assert frames[-1] == ((18.0, 18.0), magnet_size(True))
    assert widget.view.level == 0 and callbacks == [True]
    widget.visible = False
    assert not widget.contains(40, 920)
    widget.visible = True
    widget.set_compact(False)
    assert widget.contains(320, 910) and callbacks == [True, False]


def test_toggle_targets_never_select_an_autonomy_level():
    assert magnet_hit(308, 60, False) == "collapse"
    assert magnet_hit(150, 24, True) == "expand"
    assert magnet_hit(300, 24, True) is None
    assert magnet_hit(-1, 24, True) is None
    assert magnet_hit(35, 60, False) is None  # title, not an autonomy control
    assert [magnet_hit(x, 22, False) for x in (50, 160, 270)] == [0, 1, 2]


@pytest.mark.parametrize("text", ["Listening…", "Transcribing…", "Stopping…", "New request…", "Microphone error"])
def test_active_or_critical_badges_are_never_folded(text):
    assert not is_idle_badge(text, False)
    assert not is_idle_badge(text, True)


def test_idle_reminder_folds_but_shortcut_is_available_on_handle():
    assert is_idle_badge("ctrl+shift+h: new request", False)
    assert is_idle_badge("Hold ctrl+shift+h and speak", False)
    assert not is_idle_badge("ctrl+shift+h: new request", True)
    assert shortcut_label("ctrl+shift+h") == "⌃⇧H"
    assert shortcut_label("command+h") == "⌘H"


@pytest.mark.skipif(sys.platform != "darwin", reason="Native AppKit binding")
def test_compact_overlay_keeps_existing_active_badge(monkeypatch):
    from hcs_agent import overlay
    ov = overlay.Overlay.__new__(overlay.Overlay)
    ov.view = SimpleNamespace(compact_idle=False, badge=("Stopping…", True), setNeedsDisplay_=lambda _: None)
    monkeypatch.setattr(overlay, "_on_main", lambda fn: fn())
    ov.set_compact(True)
    assert ov.view.compact_idle and ov.view.badge == ("Stopping…", True)
