"""macOS pencil overlay for guide mode: a rough graphite sketch on top of the screen.

Design rules: it must look like a quick draft, never like a UI. Thin pencil strokes, a loose circle
around the control (only when the agent gave a target), a short handwritten line of text with a faint
halo so it stays readable, nothing opaque that hides the screen. Transparent, click-through,
always-on-top, and excluded from screen capture so H never sees its own annotations.
Must run on the main thread (AppKit); worker threads call `show()` / `hide()`.
"""

from __future__ import annotations

import math
import random
import threading
from typing import Callable

import AppKit
import Foundation
import objc
from Quartz import CGEventCreate, CGEventGetLocation

GRAPHITE = (0.86, 0.17, 0.12, 0.92)  # red pencil: readable on light and dark backgrounds
HAND_FONTS = ("Bradley Hand", "Noteworthy", "Marker Felt", "Chalkboard")


def mouse_position() -> tuple[float, float]:
    """Current pointer in screen points (top-left origin, like screenshots)."""
    p = CGEventGetLocation(CGEventCreate(None))
    return float(p.x), float(p.y)


def screen_size_points() -> tuple[float, float]:
    f = AppKit.NSScreen.mainScreen().frame()
    return float(f.size.width), float(f.size.height)


def _hand_font(size: float):
    for name in HAND_FONTS:
        f = AppKit.NSFont.fontWithName_size_(name, size)
        if f is not None:
            return f
    return AppKit.NSFont.systemFontOfSize_(size)


def _wobble_path(points: list[tuple[float, float]], rnd: random.Random, width: float, jitter: float):
    """A stroke drawn as 2 overlapping passes, each slightly displaced: reads as pencil, not vector."""
    paths = []
    for _ in range(2):
        path = AppKit.NSBezierPath.bezierPath()
        path.setLineWidth_(width)
        path.setLineCapStyle_(AppKit.NSLineCapStyleRound)
        first = True
        for x, y in points:
            p = (x + rnd.uniform(-jitter, jitter), y + rnd.uniform(-jitter, jitter))
            if first:
                path.moveToPoint_(p)
                first = False
            else:
                path.lineToPoint_(p)
        paths.append(path)
    return paths


class _SketchView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_SketchView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.target = None  # AppKit coords (bottom-left origin) or None
        self.text = ""
        self.seed = 1
        return self

    def isOpaque(self):
        return False

    def drawRect_(self, rect):
        if not self.text and self.target is None:
            return
        rnd = random.Random(self.seed)
        bounds = self.bounds()
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*GRAPHITE).setStroke()

        if self.target is not None:
            tx, ty = self.target
            # Loose ellipse, slightly open (a pencil circle never quite closes).
            pts = []
            for i in range(0, 40):
                a = -0.35 + i / 39 * (2 * math.pi + 0.55)
                pts.append((tx + 34 * math.cos(a) * 1.25, ty + 34 * math.sin(a)))
            for path in _wobble_path(pts, rnd, 1.6, 1.8):
                path.stroke()
            # Text sits up-right of the circle, or up-left near the right edge; a short stroke links them.
            right = tx + 240 < bounds.size.width
            anchor_x = tx + 48 if right else tx - 48
            text_x = anchor_x if right else anchor_x - 230
            text_y = min(ty + 34, bounds.size.height - 60)
            link = [(tx + (40 if right else -40), ty + 14), (anchor_x + (6 if right else -6), text_y - 2)]
            for path in _wobble_path(link, rnd, 1.3, 1.2):
                path.stroke()
        else:
            # No target: a one-line draft at the top of the screen, like a note in the margin.
            text_x, text_y = bounds.size.width / 2 - 170, bounds.size.height - 92

        font = _hand_font(19)
        attrs = {
            AppKit.NSFontAttributeName: font,
            AppKit.NSForegroundColorAttributeName: AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*GRAPHITE),
        }
        s = Foundation.NSString.stringWithString_(self.text)
        s.drawInRect_withAttributes_(((text_x, text_y), (340, 50)), attrs)
        # A quick underline squiggle under the text, the way you'd stress a note.
        under = [(text_x + i * 24, text_y - 3 + (2 if i % 2 else -2)) for i in range(0, 7)]
        for path in _wobble_path(under, rnd, 1.0, 1.0):
            path.stroke()


class Overlay:
    """Owns the overlay window. Create and drive from the main thread; `show`/`hide` are thread-safe."""

    def __init__(self) -> None:
        self.app = AppKit.NSApplication.sharedApplication()
        self.app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        frame = AppKit.NSScreen.mainScreen().frame()
        self._screen_h = frame.size.height
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setIgnoresMouseEvents_(True)
        self.window.setLevel_(AppKit.NSScreenSaverWindowLevel)
        self.window.setSharingType_(AppKit.NSWindowSharingNone)  # invisible to screen capture (and to H)
        self.window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorStationary)
        self.view = _SketchView.alloc().initWithFrame_(self.window.contentView().bounds())
        self.window.setContentView_(self.view)
        self._seed = 1

    # ------------------------------------------------------------------ API (any thread)

    def show(self, text: str, target: tuple[float, float] | None = None) -> None:
        """Draw a short note; circle `target` (screen points, top-left origin) when given."""
        self._seed += 1

        def apply() -> None:
            self.view.target = None if target is None else (target[0], self._screen_h - target[1])
            self.view.text = text[:90]
            self.view.seed = self._seed
            self.view.setNeedsDisplay_(True)
            self.window.orderFrontRegardless()

        _on_main(apply)

    def hide(self) -> None:
        def apply() -> None:
            self.view.target = None
            self.view.text = ""
            self.view.setNeedsDisplay_(True)
            self.window.orderOut_(None)

        _on_main(apply)

    # ------------------------------------------------------------------ main loop

    def run_until(self, done: Callable[[], bool], tick: Callable[[], None] | None = None, interval: float = 0.2) -> None:
        """Pump the AppKit run loop on the main thread until `done()`; `tick()` runs every interval."""
        while not done():
            if tick:
                tick()
            until = Foundation.NSDate.dateWithTimeIntervalSinceNow_(interval)
            while True:
                event = self.app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                    AppKit.NSEventMaskAny, until, Foundation.NSDefaultRunLoopMode, True)
                if event is None:
                    break
                self.app.sendEvent_(event)
        self.hide()


def _on_main(fn: Callable[[], None]) -> None:
    if threading.current_thread() is threading.main_thread():
        fn()
        return
    _Block.alloc().initWithFn_(fn).performSelectorOnMainThread_withObject_waitUntilDone_("run:", None, False)


class _Block(Foundation.NSObject):
    def initWithFn_(self, fn):
        self = objc.super(_Block, self).init()
        self.fn = fn
        return self

    def run_(self, _):
        self.fn()
