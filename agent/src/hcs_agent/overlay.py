"""macOS pencil overlay for guide mode: a rough red-pencil draft on paper scraps over the screen.

Design rules: it must look like a quick draft, never like a UI. Thin pencil strokes, loose circles and
boxes around controls, arrows from notes to targets, handwritten text on small white paper cutouts.
Transparent, click-through, always-on-top, excluded from screen capture so H never sees its own marks.
Must run on the main thread (AppKit); worker threads call `show()` / `hide()`.

A `Scene` is what gets drawn: a list of `Mark`s (circle / box / underline / label / arrow) plus an
optional main note and a secondary "why" note.
"""

from __future__ import annotations

import math
import random
import threading
from dataclasses import dataclass, field
from typing import Callable, Literal

import AppKit
import Foundation
import objc
from Quartz import CGEventCreate, CGEventGetLocation

GRAPHITE = (0.86, 0.17, 0.12, 0.92)  # red pencil: readable on light and dark backgrounds
PAPER = (1.0, 1.0, 0.985, 0.93)
PAPER_SOFT = (1.0, 1.0, 0.985, 0.80)
HAND_FONTS = ("Bradley Hand", "Noteworthy", "Marker Felt", "Chalkboard")

Shape = Literal["circle", "box", "underline", "label", "arrow"]


@dataclass
class Mark:
    shape: Shape
    xy: tuple[float, float]  # screen points, top-left origin
    text: str = ""
    size: tuple[float, float] = (0, 0)  # box: width/height in points; 0 = default
    to: tuple[float, float] | None = None  # arrow end


@dataclass
class Scene:
    text: str = ""  # main instruction (goes on the big paper note)
    target: tuple[float, float] | None = None  # main control: circle + arrow from the note
    why: str = ""  # secondary explanation (lighter note under the main one)
    marks: list[Mark] = field(default_factory=list)
    step: int | None = None


def mouse_position() -> tuple[float, float]:
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


def _ink():
    return AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*GRAPHITE)


def _wobble_path(points, rnd: random.Random, width: float, jitter: float):
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


def _stroke(points, rnd, width=1.5, jitter=1.4):
    for path in _wobble_path(points, rnd, width, jitter):
        path.stroke()


def _circle(cx, cy, rnd, rx=42, ry=34):
    pts = []
    for i in range(0, 40):
        a = -0.35 + i / 39 * (2 * math.pi + 0.55)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    _stroke(pts, rnd, 1.6, 1.8)


def _box(x, y, w, h, rnd):
    pts = [(x, y), (x + w, y + 2), (x + w - 2, y + h), (x + 1, y + h - 2), (x, y + 4)]
    _stroke(pts, rnd, 1.5, 2.0)


def _arrow(start, end, rnd, width=1.4):
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 10)
    _stroke([start, mid, end], rnd, width, 1.2)
    ang = math.atan2(end[1] - mid[1], end[0] - mid[0])
    for side in (-1, 1):
        a = ang + math.pi + side * 0.45
        _stroke([end, (end[0] + 20 * math.cos(a), end[1] + 20 * math.sin(a))], rnd, width, 0.8)


def _draw_paper(x, y, w, h, rnd, color=PAPER):
    """A scrap of white paper: roughly cut edges, slight tilt, soft shadow (cutout collage)."""
    tilt = rnd.uniform(-0.03, 0.03)
    cx, cy = x + w / 2, y + h / 2

    def rot(px, py):
        dx, dy = px - cx, py - cy
        return (cx + dx * math.cos(tilt) - dy * math.sin(tilt), cy + dx * math.sin(tilt) + dy * math.cos(tilt))

    pts = []
    for (ax, ay), (bx, by), n in (((x, y), (x + w, y), 5), ((x + w, y), (x + w, y + h), 3),
                                  ((x + w, y + h), (x, y + h), 5), ((x, y + h), (x, y), 3)):
        for i in range(n):
            t = i / n
            pts.append(rot(ax + (bx - ax) * t + rnd.uniform(-3, 3), ay + (by - ay) * t + rnd.uniform(-3, 3)))
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
    AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*color).setFill()
    path.fill()
    AppKit.NSGraphicsContext.restoreGraphicsState()


def _measure(text, size, max_w):
    attrs = {AppKit.NSFontAttributeName: _hand_font(size), AppKit.NSForegroundColorAttributeName: _ink()}
    s = Foundation.NSString.stringWithString_(text)
    bound = s.boundingRectWithSize_options_attributes_((max_w, 400), 1 << 0, attrs).size
    return attrs, s, min(bound.width, max_w) + 2, bound.height + 2


def _clamp(x, y, w, h, W, H, margin=14):
    """Keep a paper of size (w, h) anchored at (x, y) inside the screen."""
    return min(max(x, margin), W - w - margin), min(max(y, margin), H - h - margin)


def _note(x, y, text, rnd, size=19, max_w=340, color=PAPER, underline=True, bounds=None) -> tuple[float, float, float, float]:
    """Handwritten text on a paper scrap, anchored at its bottom-left. Returns (x, y, width, height) drawn."""
    attrs, s, tw, th = _measure(text, size, max_w)
    if bounds is not None:
        x, y = _clamp(x, y, tw + 20, th + 12, bounds[0], bounds[1])
    _draw_paper(x - 10, y - 6, tw + 20, th + 12, rnd, color)
    _ink().setStroke()
    s.drawInRect_withAttributes_(((x, y), (max_w, th + 4)), attrs)
    if underline:
        _stroke([(x + i * (tw / 6), y - 3 + (2 if i % 2 else -2)) for i in range(0, 7)], rnd, 1.0, 1.0)
    return x, y, tw + 20, th + 12


class _SketchView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_SketchView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.scene = None  # Scene with AppKit coords (bottom-left origin)
        self.seed = 1
        self.badge = None  # (text, pulsing) or None: the "listening" indicator
        return self

    def isOpaque(self):
        return False

    def drawRect_(self, rect):
        if self.badge is not None:
            self._draw_badge()
        sc = self.scene
        if sc is None or (not sc.text and sc.target is None and not sc.marks):
            return
        rnd = random.Random(self.seed)
        bounds = self.bounds()
        W, H = bounds.size.width, bounds.size.height
        _ink().setStroke()

        # Secondary marks first (they sit "under" the main note).
        for m in sc.marks:
            mx, my = m.xy
            if m.shape == "circle":
                _circle(mx, my, rnd, 36, 30)
            elif m.shape == "box":
                w, h = (m.size[0] or 160), (m.size[1] or 60)
                _box(mx - w / 2, my - h / 2, w, h, rnd)
            elif m.shape == "underline":
                _stroke([(mx - 60 + i * 24, my - 10 + (2 if i % 2 else -2)) for i in range(0, 6)], rnd, 1.4, 1.2)
            elif m.shape == "arrow" and m.to:
                _arrow(m.xy, m.to, rnd)
            if m.text and m.shape != "arrow":
                # Small label next to the mark, with a short link stroke.
                lx = mx + 50 if mx + 300 < W else mx - 50 - 220
                ly = my + 26
                lx, ly, lw, lh = _note(lx, ly, m.text, rnd, size=15, max_w=220, color=PAPER_SOFT, underline=False, bounds=(W, H))
                _stroke([(mx + (34 if lx > mx else -34), my + 8), (lx + (-4 if lx > mx else lw - 24), ly - 2)], rnd, 1.1, 1.0)

        # Main note + circle + arrow.
        if sc.target is not None:
            tx, ty = sc.target
            _circle(tx, ty, rnd)
            label = f"{sc.step}. {sc.text}" if sc.step else sc.text
            _, _, lw, lh = _measure(label, 19, 340)
            right = tx + 48 + lw + 40 < W
            text_x = tx + 48 if right else tx - 48 - lw
            text_y = ty + 40
            text_x, text_y, w, h = _note(text_x, text_y, label, rnd, bounds=(W, H))
            if sc.why:
                _, _, ww, wh = _measure(sc.why, 14, 300)
                _note(text_x + 6, text_y - 20 - wh, sc.why, rnd, size=14, max_w=300, color=PAPER_SOFT, underline=False, bounds=(W, H))
            _arrow((text_x + (6 if right else w - 26), text_y - 12), (tx + (46 if right else -46), ty + 16), rnd)
        elif sc.text:
            _, _, lw, lh = _measure(sc.text, 19, 340)
            text_x, text_y, w, h = _note(W / 2 - lw / 2, H - 92, sc.text, rnd, bounds=(W, H))
            if sc.why:
                _, _, ww, wh = _measure(sc.why, 14, 300)
                _note(text_x + 6, text_y - 20 - wh, sc.why, rnd, size=14, max_w=300, color=PAPER_SOFT, underline=False, bounds=(W, H))

    def _draw_badge(self):
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
        attrs = {AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(14),
                 AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor()}
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

    def _flip(self, xy):
        return None if xy is None else (xy[0], self._screen_h - xy[1])

    # ------------------------------------------------------------------ API (any thread)

    def show_scene(self, scene: Scene) -> None:
        self._seed += 1
        flipped = Scene(
            text=scene.text[:110], target=self._flip(scene.target), why=scene.why[:160], step=scene.step,
            marks=[Mark(m.shape, self._flip(m.xy), m.text[:60], m.size, self._flip(m.to)) for m in scene.marks],
        )

        def apply() -> None:
            self.view.scene = flipped
            self.view.seed = self._seed
            self.view.setNeedsDisplay_(True)
            self.window.orderFrontRegardless()

        _on_main(apply)

    def show(self, text: str, target: tuple[float, float] | None = None) -> None:
        """Back-compat: a note, optionally circling `target` (screen points, top-left origin)."""
        self.show_scene(Scene(text=text, target=target))

    def hide(self) -> None:
        def apply() -> None:
            self.view.scene = None
            self.view.setNeedsDisplay_(True)
            if self.view.badge is None:
                self.window.orderOut_(None)

        _on_main(apply)

    def badge(self, text: str | None, pulsing: bool = False) -> None:
        def apply() -> None:
            self.view.badge = None if text is None else (text, pulsing)
            self.view.setNeedsDisplay_(True)
            if self.view.badge is None and self.view.scene is None:
                self.window.orderOut_(None)
            else:
                self.window.orderFrontRegardless()

        _on_main(apply)

    def redraw(self) -> None:
        _on_main(lambda: self.view.setNeedsDisplay_(True))

    # ------------------------------------------------------------------ main loop

    def run_until(self, done: Callable[[], bool], tick: Callable[[], None] | None = None, interval: float = 0.2,
                  hide_at_end: bool = True) -> None:
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
