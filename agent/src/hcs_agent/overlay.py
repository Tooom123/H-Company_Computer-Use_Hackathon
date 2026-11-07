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


PAPER = (1.0, 1.0, 0.985, 0.93)


def _draw_paper(x: float, y: float, w: float, h: float, rnd: random.Random) -> None:
    """A scrap of white paper behind the note: roughly cut edges, slight tilt, soft shadow (cutout collage)."""
    tilt = rnd.uniform(-0.03, 0.03)
    cx, cy = x + w / 2, y + h / 2

    def rot(px: float, py: float) -> tuple[float, float]:
        dx, dy = px - cx, py - cy
        return (cx + dx * math.cos(tilt) - dy * math.sin(tilt), cy + dx * math.sin(tilt) + dy * math.cos(tilt))

    # Walk the rectangle edge with a few uneven cuts per side.
    pts = []
    for side, n in (((x, y), (x + w, y)), 5), (((x + w, y), (x + w, y + h)), 3), (((x + w, y + h), (x, y + h)), 5), (((x, y + h), (x, y)), 3):
        (ax, ay), (bx, by) = side
        for i in range(n):
            t = i / n
            jx, jy = rnd.uniform(-3, 3), rnd.uniform(-3, 3)
            pts.append(rot(ax + (bx - ax) * t + jx, ay + (by - ay) * t + jy))
    path = AppKit.NSBezierPath.bezierPath()
    path.moveToPoint_(pts[0])
    for pt in pts[1:]:
        path.lineToPoint_(pt)
    path.closePath()
    AppKit.NSGraphicsContext.saveGraphicsState()
    shadow = AppKit.NSShadow.alloc().init()
    shadow.setShadowOffset_((2, -3))
    shadow.setShadowBlurRadius_(6)
    shadow.setShadowColor_(AppKit.NSColor.colorWithCalibratedWhite_alpha_(0, 0.35))
    shadow.set()
    AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*PAPER).setFill()
    path.fill()
    AppKit.NSGraphicsContext.restoreGraphicsState()


class _SketchView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_SketchView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.target = None  # AppKit coords (bottom-left origin) or None
        self.text = ""
        self.seed = 1
        self.badge = None  # (text, pulsing) or None: the "listening" indicator
        return self

    def isOpaque(self):
        return False

    def drawRect_(self, rect):
        if self.badge is not None:
            self._draw_badge()
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
            # Arrow from the note down to the circle, with a rough two-stroke head at the circle end.
            start = (anchor_x + (6 if right else -6), text_y - 12)
            end = (tx + (44 if right else -44), ty + 16)
            mid = ((start[0] + end[0]) / 2 + (0 if right else 0), (start[1] + end[1]) / 2 + 10)
            for path in _wobble_path([start, mid, end], rnd, 1.4, 1.2):
                path.stroke()
            ang = math.atan2(end[1] - mid[1], end[0] - mid[0])
            for side in (-1, 1):
                a = ang + math.pi + side * 0.45
                head = [(end[0], end[1]), (end[0] + 20 * math.cos(a), end[1] + 20 * math.sin(a))]
                for path in _wobble_path(head, rnd, 1.4, 0.8):
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
        size = s.boundingRectWithSize_options_attributes_((340, 60), 1 << 0, attrs).size  # wraps on width
        tw, th = min(size.width, 340) + 2, size.height + 2
        _draw_paper(text_x - 10, text_y - 6, tw + 20, th + 12, rnd)
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*GRAPHITE).setStroke()
        s.drawInRect_withAttributes_(((text_x, text_y), (340, th + 4)), attrs)
        # A quick underline squiggle under the text, the way you'd stress a note.
        under = [(text_x + i * (tw / 6), text_y - 3 + (2 if i % 2 else -2)) for i in range(0, 7)]
        for path in _wobble_path(under, rnd, 1.0, 1.0):
            path.stroke()


    def _draw_badge(self):
        """Small pill at the bottom centre: a red dot (pulsing while recording) and a short label."""
        import time

        text, pulsing = self.badge
        bounds = self.bounds()
        w, h = 210.0, 36.0
        x, y = bounds.size.width / 2 - w / 2, 28.0
        pill = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(((x, y), (w, h)), h / 2, h / 2)
        AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.08, 0.88).setFill()
        pill.fill()
        alpha = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(time.time() * 6)) if pulsing else 1.0
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.23, 0.2, alpha).setFill()
        AppKit.NSBezierPath.bezierPathWithOvalInRect_(((x + 14, y + h / 2 - 7), (14, 14))).fill()
        attrs = {
            AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(14),
            AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor(),
        }
        Foundation.NSString.stringWithString_(text).drawInRect_withAttributes_(((x + 38, y + 8), (w - 46, 20)), attrs)


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
            if self.view.badge is None:
                self.window.orderOut_(None)

        _on_main(apply)

    def badge(self, text: str | None, pulsing: bool = False) -> None:
        """Show (or clear with None) the listening indicator."""

        def apply() -> None:
            self.view.badge = None if text is None else (text, pulsing)
            self.view.setNeedsDisplay_(True)
            if self.view.badge is None and not self.view.text and self.view.target is None:
                self.window.orderOut_(None)
            else:
                self.window.orderFrontRegardless()

        _on_main(apply)

    def redraw(self) -> None:
        _on_main(lambda: self.view.setNeedsDisplay_(True))

    # ------------------------------------------------------------------ main loop

    def run_until(self, done: Callable[[], bool], tick: Callable[[], None] | None = None, interval: float = 0.2,
                  hide_at_end: bool = True) -> None:
        """Pump the AppKit run loop on the main thread until `done()`; `tick()` runs every interval."""
        while not done():
            if tick:
                tick()
            if self.view.badge is not None and self.view.badge[1]:
                self.view.setNeedsDisplay_(True)  # pulse
            until = Foundation.NSDate.dateWithTimeIntervalSinceNow_(interval)
            while True:
                event = self.app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                    AppKit.NSEventMaskAny, until, Foundation.NSDefaultRunLoopMode, True)
                if event is None:
                    break
                self.app.sendEvent_(event)
        if hide_at_end:
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
