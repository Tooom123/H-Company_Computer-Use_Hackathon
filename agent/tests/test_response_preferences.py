"""Local presentation choices never change task execution or recorded evidence."""
import sys
from types import SimpleNamespace

import pytest

from hcs_agent import cli


@pytest.fixture
def rig(monkeypatch):
    calls, text = [], []
    speaker = SimpleNamespace(muted=False, speaking=False,
                              stop=lambda: calls.append("stop"),
                              say=lambda *s, **kw: calls.append(s))
    monkeypatch.setattr(cli, "_SPEECH", {"speaker": speaker, "ready": True})
    monkeypatch.setattr(cli, "_PRESENTATION", {"mode": "both", "overlay": SimpleNamespace(set_text_enabled=text.append)})
    monkeypatch.setitem(cli._MAGNET, "current", None)
    monkeypatch.setattr(cli, "_voice_input_active", lambda: False)
    return SimpleNamespace(speaker=speaker, calls=calls, text=text)


def test_live_mode_transitions_stop_audio_and_preserve_guidance(rig):
    assert cli._control_voice({"response_mode": "voice"})["response_mode"] == "voice"
    assert rig.text[-1] is False
    cli._say("Look at the Answer panel.")
    assert rig.calls == [("Look at the Answer panel.",)]
    assert cli._control_voice({"response_mode": "text"})["enabled"] is False
    cli._say("This must remain silent.")
    assert rig.calls[-1] == "stop" and len(rig.calls) == 2
    assert rig.text[-1] is True
    assert cli._control_voice({"response_mode": "both"})["enabled"] is True
    assert rig.text[-1] is True
    cli._say("Here is the answer.")
    assert rig.calls[-1] == ("Here is the answer.",)


def test_missing_speaker_never_hides_the_only_response(rig, monkeypatch):
    monkeypatch.setitem(cli._SPEECH, "speaker", None)
    status = cli._control_voice({"response_mode": "voice"})
    assert status["response_mode"] == "text" and not status["enabled"]
    assert rig.text == [True]


def test_legacy_voice_switch_remains_consistent_with_new_modes(rig):
    cli._control_voice({"response_mode": "voice"})
    assert cli._control_voice({"enabled": False})["response_mode"] == "text"
    assert cli._control_voice({"enabled": True})["response_mode"] == "both"


@pytest.mark.skipif(sys.platform != "darwin", reason="Native AppKit drawing")
def test_voice_only_keeps_target_marker_and_original_text_for_restore(monkeypatch):
    from hcs_agent import overlay
    monkeypatch.setattr(overlay, "_on_main", lambda f: f())
    monkeypatch.setattr(overlay, "_ink", lambda: SimpleNamespace(setStroke=lambda: None))
    monkeypatch.setattr(overlay, "_measure", lambda *a: (None, None, 180, 30))
    notes, frames = [], []
    monkeypatch.setattr(overlay, "_note", lambda *a, **kw: notes.append(a[2]))
    monkeypatch.setattr(overlay, "_frame", lambda *a, **kw: frames.append(a[:2]))
    monkeypatch.setattr(overlay, "_arrow", lambda *a: None)
    view = overlay._SketchView.alloc().initWithFrame_(((0, 0), (1470, 956)))
    scene = overlay.Scene(text="Read the answer here.", target=(450, 400))
    view.scene = scene
    ov = overlay.Overlay.__new__(overlay.Overlay)
    ov.view = view
    ov.set_text_enabled(False)
    view.drawRect_(view.bounds())
    assert not notes and frames == [(450, 400)]
    assert view.scene is scene and view.scene.text == "Read the answer here."
    assert ov.reading_duration == 0
    ov.set_text_enabled(True)
    view.drawRect_(view.bounds())
    assert notes == ["Read the answer here."]
    assert frames == [(450, 400), (450, 400)]


@pytest.mark.skipif(sys.platform != "darwin", reason="Native AppKit drawing")
def test_shortcut_paper_expires_but_listening_and_errors_remain(monkeypatch):
    from hcs_agent import overlay
    clock = [100.0]
    monkeypatch.setattr(overlay.time, "monotonic", lambda: clock[0])
    view = overlay._SketchView.alloc().initWithFrame_(((0, 0), (1470, 956)))
    class Painted(Exception):
        pass
    def measure(*args):
        raise Painted  # reached drawing; no window or graphics context needed
    monkeypatch.setattr(overlay, "_measure", measure)
    view.badge = ("Hold Right ⌥ and say what you need", False)
    clock[0] = 109.9
    with pytest.raises(Painted):
        view._draw_badge()
    clock[0] = 110.0
    view._draw_badge()
    # An idle reminder after a task may not restart its 10-second lifetime.
    view.badge = ("Right ⌥: new request", False)
    clock[0] = 180.0
    view._draw_badge()
    for text, pulsing in [("Listening…", True), ("Stopping…", False), ("Microphone error", False)]:
        view.badge = (text, pulsing)
        with pytest.raises(Painted):
            view._draw_badge()
