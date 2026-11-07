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
    "name": "point",
    "description": "Point at the best candidate for the requested control and say whether it really is that control.",
    "parameters": {"type": "object", "properties": {
        "x": {"type": "integer"}, "y": {"type": "integer"},
        "is_the_control": {"type": "boolean",
                           "description": "true only if the pointed element is exactly the requested control, visible now"},
        "seen": {"type": "string", "description": "What the pointed element actually is, 5 words."}},
        "required": ["x", "y", "is_the_control", "seen"]}}}
_NOT_FOUND = {"type": "function", "function": {
    "name": "not_found", "description": "The requested control is not visible on this screen.",
    "parameters": {"type": "object", "properties": {"what_is_visible": {"type": "string"}},
                   "required": ["what_is_visible"]}}}
_TOOLS = [_POINT, _NOT_FOUND]
_CHECK = {"type": "function", "function": {
    "name": "screen_check",
    "description": "Report whether the expected screen is displayed.",
    "parameters": {"type": "object", "properties": {
        "matches": {"type": "boolean", "description": "True if the described screen is what is displayed."},
        "what_is_visible": {"type": "string", "description": "Which app and which page is displayed, in a few words."}},
        "required": ["matches", "what_is_visible"]}}}


@dataclass
class Located:
    found: bool
    screen_xy: tuple[int, int] | None
    visible: str = ""
    latency_s: float = 0.0


def capture(width: int = GROUNDING_WIDTH) -> tuple[str, tuple[int, int], tuple[float, float]]:
    """Screenshot of the main display -> (jpeg base64 scaled to `width`, (img_w, img_h), (screen_w_pts, screen_h_pts))."""
    from PIL import Image
    from hai_drivers.desktop.local import LocalDesktopDriver

    from .overlay import screen_size_points

    d = LocalDesktopDriver()
    try:
        raw = base64.b64decode(d.screenshot_b64())
    finally:
        d.close()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
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
        r = self._http.post(f"{H_MODELS_URL}/chat/completions", json=body)
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
        prompt = f"{context + ' ' if context else ''}Point at: {description}."
        if strict:
            prompt += " If it is really not on this screen, call not_found and describe what is visible instead."
        fn, args = self._call(img_b64, prompt, _TOOLS if strict else [_POINT])
        latency = time.time() - t0
        if fn and fn["name"] == "point" and "x" in args and "y" in args:
            # Holo returns coordinates normalised to [0, 1000] on the image it was sent. It always points at
            # something; `is_the_control` tells whether that something is really the requested element.
            xy = (int(int(args["x"]) / 1000 * sw), int(int(args["y"]) / 1000 * sh))
            really = args.get("is_the_control", True)
            return Located(bool(really), xy if really else None, args.get("seen", ""), latency)
        return Located(False, None, args.get("what_is_visible", ""), latency)

    def screen_matches(self, expected: str) -> tuple[bool, str]:
        """Is the expected screen displayed? Returns (matches, what is visible)."""
        img_b64, _, _ = capture(768)
        fn, args = self._call(img_b64, f"Expected screen: {expected}. Is this what is displayed?", [_CHECK])
        return bool(args.get("matches")), args.get("what_is_visible", "")
