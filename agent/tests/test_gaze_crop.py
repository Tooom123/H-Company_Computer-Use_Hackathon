"""Vision opt-in: gaze state, crop choice, control routes, and the crop-first locate with its fallback."""

from __future__ import annotations

import json
import sys
import time
import types
import urllib.error
import urllib.request

import pytest
from PIL import Image

from hcs_agent import gaze_crop
from hcs_agent.gaze_crop import Element, GazeState, choose_crop, intent_score


def test_off_by_default_and_gaze_ignored_when_off(monkeypatch):
    monkeypatch.delenv("HCS_VISION", raising=False)
    g = GazeState()
    assert g.enabled is False
    g.push(100, 100)
    assert g.point() is None and g.snapshot()["gaze_age_s"] is None


def test_point_is_the_recent_median_and_expires():
    g = GazeState()
    g.set_enabled(True)
    now = time.time()
    for i, (x, y) in enumerate([(100, 100), (110, 104), (900, 900), (104, 98)]):
        g.push(x, y, t=now - 0.3 + i * 0.05)
    assert g.point(now) == (107.0, 102.0)  # the outlier does not move the median much
    assert g.point(now + 5) is None  # stale gaze = not where the user looks now
    g.push(10, 10, error_px=150)
    assert g.snapshot()["error_px"] == 150 and g.snapshot()["live"]
    g.set_enabled(False)
    assert g.point() is None


def test_intent_matches_paraphrases():
    assert intent_score("je veux supprimer ma clé API", "Delete key") == 1.0
    assert intent_score("create a new opportunity", "New") == 1.0
    assert intent_score("open the settings", "Log in") == 0.0


def test_crop_gaze_only_and_with_controls():
    screen = (1440, 900)
    (x, y, w, h), how = choose_crop((700, 400), 120, screen)
    assert how == "g" and w >= 768 and h >= 480 and x <= 700 <= x + w and y <= 400 <= y + h
    # the gaze sits halfway between two controls: the one the request names wins the crop
    els = [Element("Delete key", (100, 400, 90, 30)), Element("Copy link", (1250, 400, 90, 30))]
    (x, y, w, h), how = choose_crop((720, 415), 300, screen, els, "je veux supprimer ma clé")
    assert how == "gci" and x <= 100 and x + w >= 190 and x + w < 1250
    (x, y, w, h), _ = choose_crop((720, 415), 300, screen, els, "copy the link")
    assert x <= 1250 and x + w >= 1340 and x > 190
    # the crop scales with the screen (sizes were measured on 1440 pt)
    (_, _, w2, _), _ = choose_crop((700, 400), 120, (2880, 1800))
    assert w2 >= 1536


def _rig(monkeypatch, answer):
    """A Grounder with a fake screen (1440x900 pt, 2x pixels) and a fake Holo returning `answer`."""
    from hcs_agent import grounding

    calls = []
    overlay = types.ModuleType("hcs_agent.overlay")
    overlay.screen_size_points = lambda: (1440.0, 900.0)
    monkeypatch.setitem(sys.modules, "hcs_agent.overlay", overlay)
    monkeypatch.setattr(grounding, "grab_screen", lambda: Image.new("RGB", (2880, 1800), "white"))
    monkeypatch.setattr(grounding, "capture", lambda width=1024: ("img", (1024, 640), (1440.0, 900.0)))
    g = grounding.Grounder.__new__(grounding.Grounder)

    def fake_call(img_b64, prompt, tools):
        calls.append(prompt)
        return answer(len(calls))

    g._call = fake_call
    st = GazeState()
    st.set_enabled(True)
    monkeypatch.setattr(gaze_crop, "STATE", st)
    return g, st, calls


def test_locate_uses_the_crop_and_maps_back(monkeypatch):
    box = {"x1": 500, "y1": 500, "x2": 500, "y2": 500, "is_the_control": True, "seen": "Save"}
    g, st, calls = _rig(monkeypatch, lambda n: ({"name": "locate"}, box))
    st.push(700, 450)
    hit = g.locate("the Save button")
    (x, y, w, h), _ = choose_crop((700, 450), 120, (1440, 900))
    assert hit.found and hit.screen_xy == (int(x + w / 2), int(y + h / 2))  # centre of the crop, in screen points
    assert len(calls) == 1 and "not_found" in calls[0] and st.stats["crops"] == 1


def test_not_here_falls_back_to_the_full_screen(monkeypatch):
    answers = [({"name": "not_found"}, {"what_is_visible": "a menu"}),
               ({"name": "locate"}, {"x1": 100, "y1": 100, "x2": 100, "y2": 100, "seen": "Save"})]
    g, st, calls = _rig(monkeypatch, lambda n: answers[n - 1])
    st.push(700, 450)
    hit = g.locate("the Save button")
    assert len(calls) == 2 and hit.screen_xy == (144, 90) and st.stats["fallbacks"] == 1


def test_no_gaze_or_strict_means_the_usual_full_screen(monkeypatch):
    g, st, calls = _rig(monkeypatch, lambda n: ({"name": "locate"}, {"x1": 0, "y1": 0, "x2": 0, "y2": 0}))
    g.locate("the Save button")  # vision on, but no gaze yet
    assert len(calls) == 1 and "not_found" not in calls[0] and st.stats["full_no_gaze"] == 1
    st.push(700, 450)
    g.locate("the expected screen", strict=True)  # screen checks never use the crop
    assert st.stats["crops"] == 0


def test_control_routes(tmp_path, monkeypatch):
    from hcs_agent.control import ControlServer, Controller

    st = GazeState()
    monkeypatch.setattr(gaze_crop, "STATE", st)
    presence = []
    ctl = Controller(tmp_path, status=dict, set_autonomy=lambda _: None, stop=lambda: False,
                     set_voice=lambda o: o, test_voice=lambda: False, on_app_presence=presence.append)
    srv = ControlServer(ctl, port=0).start()
    base = f"http://127.0.0.1:{srv.port}"

    def call(path, body, headers):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        assert call("/gaze", {"x": 1, "y": 2}, {"X-HCS-Gaze": "1"}) == (200, {"accepted": False})  # off: dropped
        assert call("/vision", {"enabled": "yes"}, {"X-HCS-App": "1"})[0] == 400
        code, snap = call("/vision", {"enabled": True}, {"X-HCS-App": "1"})
        assert code == 200 and snap["enabled"] is True
        assert call("/gaze", {"x": 10, "y": 20, "error_px": 140}, {"X-HCS-Gaze": "1"}) == (200, {"accepted": True})
        assert st.point() == (10.0, 20.0) and st.error_px == 140
        assert call("/gaze", {"x": "a", "y": 2}, {"X-HCS-Gaze": "1"})[0] == 400
        assert call("/vision", {"enabled": False}, {"X-HCS-Gaze": "1"})[0] == 403  # the gaze feed cannot switch it
        assert presence == [True]  # only the app's own requests count as "the app is open"
    finally:
        srv.close()
