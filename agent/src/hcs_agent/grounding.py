"""UI grounding with Holo through the H Models API: where is this control on the current screen?

Used by the scripted guide: the procedure knows the steps; Holo only localises the control on a fresh
screenshot (one call, thinking off, ~1-2 s). Coordinates come back normalised to [0, 1000] and are mapped
to screen points for the overlay.
"""

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass

import httpx

H_MODELS_URL = os.environ.get("HAI_MODELS_BASE_URL", "https://api.hcompany.ai/v1")
GROUNDING_WIDTH = 1024

_POINT = {"type": "function", "function": {
    "name": "locate",
    "description": "Locate the best candidate for the requested control: its tight bounding box, and whether it "
                   "really is that control.",
    "parameters": {"type": "object", "properties": {
        "x1": {"type": "integer", "description": "left, in [0,1000] of the image"},
        "y1": {"type": "integer", "description": "top"},
        "x2": {"type": "integer", "description": "right"},
        "y2": {"type": "integer", "description": "bottom"},
        "is_the_control": {"type": "boolean",
                           "description": "true only if the boxed element is exactly the requested control, visible now"},
        "seen": {"type": "string", "description": "What the boxed element actually is, 5 words."}},
        "required": ["x1", "y1", "x2", "y2", "is_the_control", "seen"]}}}
_NOT_FOUND = {"type": "function", "function": {
    "name": "not_found", "description": "The requested control is not visible on this screen.",
    "parameters": {"type": "object", "properties": {"what_is_visible": {"type": "string"}},
                   "required": ["what_is_visible"]}}}
_TOOLS = [_POINT, _NOT_FOUND]
_CHECK = {"type": "function", "function": {
    "name": "screen_check",
    "description": "Report whether the expected screen is displayed.",
    "parameters": {"type": "object", "properties": {
        "what_is_visible": {"type": "string", "description": "Which app and which page is in front, in a few words."},
        "matches": {"type": "boolean", "description": "True only if everything in the expected screen is visible."}},
        "required": ["what_is_visible", "matches"]}}}


@dataclass
class Located:
    found: bool
    screen_xy: tuple[int, int] | None  # centre of the element, screen points
    visible: str = ""
    latency_s: float = 0.0
    box: tuple[int, int, int, int] | None = None  # (x, y, w, h) of the element, screen points


def grab_screen():
    """Main-display screenshot as a PIL image, without touching pynput.

    Do not use LocalDesktopDriver just to take a screenshot: its constructor builds a pynput keyboard
    Controller, which calls macOS TIS keyboard APIs; done from a worker thread while the InputHub listener
    does the same, macOS aborts the whole process (SIGABRT, the "silent exits").
    """
    import pyautogui

    return pyautogui.screenshot()


def capture(width: int = GROUNDING_WIDTH) -> tuple[str, tuple[int, int], tuple[float, float]]:
    """Screenshot of the main display -> (jpeg base64 scaled to `width`, (img_w, img_h), (screen_w_pts, screen_h_pts))."""
    from .overlay import screen_size_points

    img = grab_screen().convert("RGB")
    scale = width / img.width
    img = img.resize((width, int(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode(), (img.width, img.height), screen_size_points()


class Grounder:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        from hai_agents.client import default_api_key

        self.api_key = api_key or default_api_key()
        self.model = model or os.environ.get("HCS_GROUNDING_MODEL", "holo4-35b-a3b")
        self._http = httpx.Client(timeout=30, headers={"Authorization": f"Bearer {self.api_key}"})

    def _call(self, img_b64: str, prompt: str, tools: list) -> tuple[dict | None, dict]:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": prompt},
            ]}],
            "tools": tools,
            "tool_choice": "required",
            "temperature": 0,
            "max_tokens": 200,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        for attempt in range(4):
            r = self._http.post(f"{H_MODELS_URL}/chat/completions", json=body)
            if r.status_code != 429 or attempt == 3:
                break
            # Rate limited (bursts of locate / screen checks during a guide): back off briefly and retry.
            # Never honour a long Retry-After blindly: the user would see the guide freeze.
            time.sleep(min(float(r.headers.get("retry-after") or 0) or 1.0 * (attempt + 1), 3.0))
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return None, {}
        import json

        fn = calls[0]["function"]
        return fn, json.loads(fn.get("arguments") or "{}")

    def locate(self, description: str, context: str = "", strict: bool = False) -> Located:
        """Find `description` on the current screen.

        Default is "always point": Holo gives up far too easily when offered a not_found escape, so we only
        offer it with `strict=True` (used to confirm we are on the expected screen).
        """
        t0 = time.time()
        img_b64, (iw, ih), (sw, sh) = capture()
        prompt = (f"{context + ' ' if context else ''}Locate: {description}. Give the tight bounding box of that "
                  "element, coordinates in [0,1000] of the image (x1,y1 top-left; x2,y2 bottom-right).")
        if strict:
            prompt += " If it is really not on this screen, call not_found and describe what is visible instead."
        fn, args = self._call(img_b64, prompt, _TOOLS if strict else [_POINT])
        latency = time.time() - t0
        if fn and fn["name"] == "locate" and all(k in args for k in ("x1", "y1", "x2", "y2")):
            # Holo returns coordinates normalised to [0, 1000] on the image it was sent. It always boxes
            # something; `is_the_control` tells whether that something is really the requested element.
            x1, x2 = sorted((int(args["x1"]) / 1000 * sw, int(args["x2"]) / 1000 * sw))
            y1, y2 = sorted((int(args["y1"]) / 1000 * sh, int(args["y2"]) / 1000 * sh))
            box = (int(x1), int(y1), max(8, int(x2 - x1)), max(8, int(y2 - y1)))
            xy = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            really = args.get("is_the_control", True)
            return Located(bool(really), xy if really else None, args.get("seen", ""), latency, box if really else None)
        return Located(False, None, args.get("what_is_visible", ""), latency)

    def screen_matches(self, expected: str) -> tuple[bool, str]:
        """Is the expected screen displayed? Returns (matches, what is visible)."""
        img_b64, _, _ = capture(768)
        # Describe first, then decide: asked "is it X?" directly, Holo said yes on a terminal (seen live).
        fn, args = self._call(img_b64, "First say which application and page are in front, then decide. "
                                       f"Expected screen: {expected}. Answer matches=false if another application is "
                                       "in front or if any part of the expected screen is missing.", [_CHECK])
        return bool(args.get("matches")), args.get("what_is_visible", "")
