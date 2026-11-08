"""Pure-function tests for the pieces that have no mock path: coordinate mappings, hotkey parsing,
note placement, routing JSON extraction, defaults and vocabulary entries. No AppKit, no H, no mic."""

import sys
from datetime import date, timedelta

import pytest

from hcs_agent.backend import _agent_name, _agent_xy_to_screen, _short as short_backend, _to_screen_points
from hcs_agent.cli import _short
from hcs_agent.inputs import _CHAR_KEYCODES, _MOD_ALIASES
from hcs_agent.procedures import _resolve_default
from hcs_agent.voice import _extract_json, _vocab_entry

darwin = pytest.mark.skipif(sys.platform != "darwin", reason="AppKit geometry")


# --------------------------------------------------------------------------- coordinate mappings


def test_agent_actions_normalised_0_1_map_to_screen_points(monkeypatch):
    import hcs_agent.backend as b

    monkeypatch.setattr("hcs_agent.overlay.screen_size_points", lambda: (1512.0, 982.0), raising=False)
    assert b._agent_xy_to_screen(0.5, 0.5) == (756, 491)
    assert b._agent_xy_to_screen(0.0, 1.0) == (0, 982)
    # defensive branch: pixel coordinates of a 1280-wide screenshot
    assert b._agent_xy_to_screen(640, 400) == (756, 472)


def test_grounding_screenshot_pixels_map_to_screen_points(monkeypatch):
    monkeypatch.setattr("hcs_agent.overlay.screen_size_points", lambda: (1512.0, 982.0), raising=False)
    assert _to_screen_points(None, 10, 1024) is None
    x, y = _to_screen_points(512, 300, 1024)  # 1024-px screenshot of a 1512-pt screen -> scale 1.4766
    assert (x, y) == (756, 442)
    # screen narrower than the screenshot: no scaling
    monkeypatch.setattr("hcs_agent.overlay.screen_size_points", lambda: (800.0, 600.0), raising=False)
    assert _to_screen_points(100, 100, 1024) == (100, 100)


# --------------------------------------------------------------------------- hotkey


def test_hotkey_keycodes_and_aliases():
    assert _CHAR_KEYCODES["h"] == 4 and _CHAR_KEYCODES["a"] == 0 and _CHAR_KEYCODES["m"] == 46
    assert _MOD_ALIASES["command"] == "cmd" and _MOD_ALIASES["option"] == "alt"


@darwin
def test_input_hub_parses_combo_without_starting_listeners(monkeypatch):
    """set_combo() is pure: cmd+h -> mods {cmd}, keycode 4; a plain key keeps the pynput Key object."""
    from hcs_agent import inputs

    class FakeListener:
        def __init__(self, **kw):
            pass

        def start(self):
            pass

    import pynput

    monkeypatch.setattr(pynput.mouse, "Listener", FakeListener)
    monkeypatch.setattr(pynput.keyboard, "Listener", FakeListener)
    hub = inputs.InputHub()
    hub.set_combo("command+H")
    assert hub._combo_mods == {"cmd"} and hub._combo_keycode == 4 and hub._plain_key is None
    hub.set_combo("f9")
    assert hub._combo_mods == set() and hub.plain_key_matches(pynput.keyboard.Key.f9)


# --------------------------------------------------------------------------- overlay placement


@darwin
def test_papers_stay_on_screen_and_never_overlap():
    from hcs_agent.overlay import _clamp, _overlaps, _place

    W, H = 1512.0, 982.0
    assert _clamp(-50, -50, 100, 40, W, H) == (14, 14)
    assert _clamp(1500, 970, 100, 40, W, H) == (W - 100 - 14, H - 40 - 14)
    placed: list = []
    a = _place(600, 500, 300, 40, (W, H), placed)
    b = _place(600, 500, 300, 40, (W, H), placed)  # same spot: must be pushed away
    c = _place(610, 505, 200, 40, (W, H), placed)
    rects = [(a[0], a[1], 300, 40), (b[0], b[1], 300, 40), (c[0], c[1], 200, 40)]
    for i in range(3):
        for j in range(i + 1, 3):
            assert not _overlaps(rects[i], rects[j], pad=0), (rects[i], rects[j])
    for x, y, w, h in rects:
        assert 0 <= x and x + w <= W and 0 <= y and y + h <= H


# --------------------------------------------------------------------------- small helpers


def test_short_cuts_at_sentence_then_length():
    assert _short("Clique ici. Puis là.", 90) == "Clique ici."
    assert _short("a" * 100, 20).endswith("…") and len(_short("a" * 100, 20)) == 20
    assert short_backend("x" * 100, 10) == "x" * 9 + "…"


def test_agent_names_follow_h_rules():
    assert _agent_name("hcs-odoo_crm_followup_activity") == "hcs-odoo-crm-followup-activity"
    assert _agent_name("  Weird__Name!! ") == "weird-name"
    assert len(_agent_name("a" * 100)) <= 63


def test_relative_default_dates():
    assert _resolve_default("+7d") == (date.today() + timedelta(days=7)).isoformat()
    assert _resolve_default("Acme Demo") == "Acme Demo"


def test_extract_json_tolerates_prose_around_the_object():
    assert _extract_json('Sure! {"a": 1, "b": [1, 2]} hope it helps') == {"a": 1, "b": [1, 2]}
    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_vocabulary_entries_carry_pronunciations_for_demo_names():
    e = _vocab_entry("Acme Demo")
    assert e["value"] == "Acme Demo" and "acmé démo" in e["pronunciations"] and e["intensity"] <= 0.5
    assert "pronunciations" not in _vocab_entry("pipeline")


def test_intent_tolerates_null_fields_from_the_model():
    from hcs_agent.voice import Intent

    i = Intent.model_validate({"procedure_id": None, "mode": None, "parameters": {"opportunity": None},
                               "role": None, "goal": None, "missing": None, "question": "Which task?"})
    assert i.goal == "" and i.parameters == {} and i.missing == [] and i.mode == "act" and i.question == "Which task?"
