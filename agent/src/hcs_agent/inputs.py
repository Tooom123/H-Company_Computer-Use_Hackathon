"""One global input listener for the whole process.

pynput installs a macOS event tap per keyboard listener; running two of them (push-to-talk hotkey and
the guide's "did the user act" watcher) in one process proved unstable. This hub owns the single mouse
and keyboard listener and fans events out to subscribers. Combos with modifiers (e.g. cmd+h) can be
swallowed so the system shortcut does not fire.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

_MOD_ALIASES = {"command": "cmd", "option": "alt", "control": "ctrl"}
_MOD_KEYCODES = {54, 55, 56, 58, 59, 60, 61, 62}  # cmd, shift, alt, ctrl (left/right) on macOS
_CHAR_KEYCODES = {c: k for c, k in zip("asdfhgzxcv", range(0, 10))} | {
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "o": 31, "u": 32, "i": 34, "p": 35, "l": 37,
    "j": 38, "k": 40, "n": 45, "m": 46,
}


class InputHub:
    """Singleton: `InputHub.get()`. Subscribers get (event, payload) with event in
    click | key_down | key_up | combo_down | combo_up."""

    _instance: "InputHub | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "InputHub":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        from pynput import keyboard, mouse

        self._kb = keyboard
        self._subs: list[Callable[[str, object], None]] = []
        self._combo_mods: set[str] = set()
        self._combo_keycode: int | None = None
        self._combo_down = False
        self.last_click = 0.0
        self.last_key = 0.0

        def on_click(x, y, button, pressed):
            if pressed:
                self.last_click = time.time()
                self._emit("click", (x, y))

        def on_press(key):
            self.last_key = time.time()
            self._emit("key_down", key)

        def on_release(key):
            self._emit("key_up", key)

        self._mouse = mouse.Listener(on_click=on_click)
        self._keys = keyboard.Listener(on_press=on_press, on_release=on_release, darwin_intercept=self._intercept)
        self._mouse.start()
        self._keys.start()

    # ------------------------------------------------------------------ subscriptions

    def subscribe(self, fn: Callable[[str, object], None]) -> None:
        self._subs.append(fn)

    def unsubscribe(self, fn: Callable[[str, object], None]) -> None:
        if fn in self._subs:
            self._subs.remove(fn)

    def _emit(self, event: str, payload) -> None:
        for fn in list(self._subs):
            try:
                fn(event, payload)
            except Exception:  # noqa: BLE001 - a subscriber must never break the tap
                pass

    # ------------------------------------------------------------------ hotkey combo

    def set_combo(self, key_name: str) -> None:
        """e.g. 'cmd+h'. The combo's key events are swallowed; subscribers get combo_down / combo_up."""
        parts = [x.strip().lower() for x in key_name.split("+")]
        self._combo_mods = {_MOD_ALIASES.get(m, m) for m in parts[:-1]}
        main = parts[-1]
        key = getattr(self._kb.Key, main, None)
        self._combo_keycode = getattr(key, "vk", None) if key is not None else _CHAR_KEYCODES.get(main)
        self._plain_key = key if not self._combo_mods else None

    def _intercept(self, event_type, event):
        if self._combo_keycode is None or not self._combo_mods:
            return event
        from Quartz import (CGEventGetFlags, CGEventGetIntegerValueField, kCGEventFlagMaskAlternate,
                            kCGEventFlagMaskCommand, kCGEventFlagMaskControl, kCGEventFlagMaskShift,
                            kCGEventFlagsChanged, kCGEventKeyDown, kCGEventKeyUp, kCGKeyboardEventKeycode)

        if event_type not in (kCGEventKeyDown, kCGEventKeyUp, kCGEventFlagsChanged):
            return event
        flags = CGEventGetFlags(event)
        held = {"cmd": bool(flags & kCGEventFlagMaskCommand), "alt": bool(flags & kCGEventFlagMaskAlternate),
                "ctrl": bool(flags & kCGEventFlagMaskControl), "shift": bool(flags & kCGEventFlagMaskShift)}
        if event_type == kCGEventFlagsChanged:
            # macOS reports modifier releases as flagsChanged, not ordinary keyUp events.
            if self._combo_down and not all(held.get(m) for m in self._combo_mods):
                self._combo_down = False
                self._emit("combo_up", None)
            return event
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
        if keycode != self._combo_keycode:
            if self._combo_down and event_type == kCGEventKeyUp and keycode in _MOD_KEYCODES:
                self._combo_down = False
                self._emit("combo_up", None)
            return event
        if not all(held.get(m) for m in self._combo_mods):
            if self._combo_down:
                self._combo_down = False
                self._emit("combo_up", None)
            return event
        if event_type == kCGEventKeyDown:
            if not self._combo_down:
                self._combo_down = True
                self._emit("combo_down", None)
        else:
            self._combo_down = False
            self._emit("combo_up", None)
        return None  # swallow: the app is not hidden, Music does not open

    def plain_key_matches(self, key) -> bool:
        return self._plain_key is not None and key == self._plain_key
