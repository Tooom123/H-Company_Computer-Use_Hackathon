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
    box: tuple[float, float, float, float] | None = None  # element bounds (x, y, w, h), top-left origin


@dataclass
class Scene:
    text: str = ""  # main instruction (goes on the big paper note)
    target: tuple[float, float] | None = None  # main control: circle + arrow from the note
    why: str = ""  # secondary explanation (lighter note under the main one)
    marks: list[Mark] = field(default_factory=list)
    step: int | None = None
    doodle: str | None = None  # "check" | "asterisk" | "question"
    target_box: tuple[float, float, float, float] | None = None  # bounds of the main control


def mouse_position() -> tuple[float, float]:
    p = CGEventGetLocation(CGEventCreate(None))
    return float(p.x), float(p.y)


def screen_size_points() -> tuple[float, float]:
    f = AppKit.NSScreen.mainScreen().frame()
    return float(f.size.width), float(f.size.height)


TEXT_SCALE = 1.5  # all red handwriting is drawn 1.5x the base sizes below


def _hand_font(size: float):
    size = size * TEXT_SCALE
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


_REVEAL = {"progress": 1.0, "index": 0, "total": 1}


def _stroke(points, rnd, width=1.5, jitter=1.4):
    """Draw a pencil stroke, revealed progressively: stroke k appears when progress passes k/total."""
    i = _REVEAL["index"]
    _REVEAL["index"] = i + 1
    total = max(1, _REVEAL["total"])
    frac = max(0.0, min(1.0, _REVEAL["progress"] * total - i))
    if frac <= 0:
        return
    pts = list(points)
    if frac < 1 and len(pts) > 2:
        pts = pts[: max(2, int(len(pts) * frac))]
    for path in _wobble_path(pts, rnd, width, jitter):
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


def _rounded_box(cx, cy, w, h, rnd):
    """Loose rounded rectangle drawn in one go, corners overshooting a little."""
    r = 10
    pts = []
    for ang0, (ox, oy) in ((math.pi, (cx - w / 2 + r, cy + h / 2 - r)), (math.pi / 2, (cx + w / 2 - r, cy + h / 2 - r)),
                           (0, (cx + w / 2 - r, cy - h / 2 + r)), (-math.pi / 2, (cx - w / 2 + r, cy - h / 2 + r))):
        for k in range(5):
            a = ang0 - k / 4 * (math.pi / 2)
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    pts.append(pts[0])
    pts.append((pts[0][0] + 6, pts[0][1] - 3))
    _stroke(pts, rnd, 1.6, 1.6)


def _bracket(cx, cy, w, h, rnd):
    """Two square brackets framing the control: [  ]."""
    a = 10
    left = [(cx - w / 2 + a, cy + h / 2), (cx - w / 2, cy + h / 2), (cx - w / 2, cy - h / 2), (cx - w / 2 + a, cy - h / 2)]
    right = [(cx + w / 2 - a, cy + h / 2), (cx + w / 2, cy + h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2 - a, cy - h / 2)]
    _stroke(left, rnd, 1.8, 1.4)
    _stroke(right, rnd, 1.8, 1.4)


def _highlight(cx, cy, w, rnd):
    """A thick marker squiggle under/through a control, like highlighting a line."""
    pts = [(cx - w / 2 + i * (w / 10), cy - 12 + (3 if i % 2 else -3)) for i in range(11)]
    for path in _wobble_path(pts, rnd, 7.0, 1.0):
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.98, 0.78, 0.2, 0.45).setStroke()
        path.stroke()
    _ink().setStroke()


def _doodle(kind, cx, cy, rnd):
    """Small hand marks: asterisk (warning), check (done), question mark (unsure)."""
    if kind == "asterisk":
        for a in (0, math.pi / 3, 2 * math.pi / 3):
            _stroke([(cx - 9 * math.cos(a), cy - 9 * math.sin(a)), (cx + 9 * math.cos(a), cy + 9 * math.sin(a))], rnd, 1.6, 0.8)
    elif kind == "check":
        _stroke([(cx - 12, cy), (cx - 3, cy - 10), (cx + 14, cy + 12)], rnd, 2.4, 1.0)
    elif kind == "question":
        pts = [(cx - 6, cy + 10), (cx, cy + 14), (cx + 6, cy + 10), (cx + 5, cy + 4), (cx, cy), (cx, cy - 5)]
        _stroke(pts, rnd, 1.8, 0.8)
        _stroke([(cx, cy - 11), (cx + 1, cy - 12)], rnd, 2.2, 0.5)


def _frame(cx, cy, rnd, style, w=84, h=68, box=None):
    """Frame the main control. With the element's bounds, the mark hugs the element (padding ~8 pt) and the
    shape follows its proportions: wide controls get a rounded box / brackets, compact ones a loop."""
    if box is not None:
        bx, by, bw, bh = box
        cx, cy = bx + bw / 2, by + bh / 2  # AppKit coords already (caller flips)
        w, h = bw + 18, bh + 16
        ratio = bw / max(1.0, bh)
        if ratio > 2.2:
            (_rounded_box if style % 2 == 0 else _bracket)(cx, cy, w, h, rnd)
            if style == 3:
                _highlight(cx, cy - bh / 2 - 6, bw, rnd)
        elif ratio > 1.3:
            (_rounded_box if style in (1, 3) else lambda *a: _circle(cx, cy, rnd, w / 2 + 6, h / 2 + 4))(cx, cy, w, h, rnd)
        else:
            _circle(cx, cy, rnd, max(w, h) / 2 + 6, max(w, h) / 2 + 2)
            if style == 3:
                _circle(cx + 2, cy - 2, rnd, max(w, h) / 2 + 2, max(w, h) / 2 + 5)
        return
    if style == 0:
        _circle(cx, cy, rnd)
    elif style == 1:
        _rounded_box(cx, cy, w, h, rnd)
    elif style == 2:
        _bracket(cx, cy, w, h, rnd)
    else:
        _circle(cx, cy, rnd, 44, 32)
        _circle(cx + 3, cy - 2, rnd, 40, 36)  # a second, more careless loop


def _arrow(start, end, rnd, width=1.4):
    bend = rnd.choice((-26, -12, 10, 24))
    mid = ((start[0] + end[0]) / 2 + bend * 0.4, (start[1] + end[1]) / 2 + bend)
    # Curve sampled as a short polyline so it reveals progressively like the other strokes.
    pts = []
    for k in range(9):
        t = k / 8
        px = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * mid[0] + t * t * end[0]
        py = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * mid[1] + t * t * end[1]
        pts.append((px, py))
    _stroke(pts, rnd, width, 1.2)
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


def _overlaps(a, b, pad=8) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw + pad and ax + aw + pad > bx and ay < by + bh + pad and ay + ah + pad > by


def _place(x, y, w, h, bounds, placed):
    """Clamp inside the screen, then push the paper down/up until it overlaps no other paper."""
    W, H = bounds
    x, y = _clamp(x, y, w, h, W, H)
    for step in range(0, 12):
        cand = (x, y - step * (h + 10)) if step % 2 == 0 else (x, y + ((step + 1) // 2) * (h + 10))
        cx, cy = _clamp(cand[0], cand[1], w, h, W, H)
        if not any(_overlaps((cx, cy, w, h), r) for r in placed):
            placed.append((cx, cy, w, h))
            return cx, cy
    placed.append((x, y, w, h))
    return x, y


def _note(x, y, text, rnd, size=19, max_w=480, color=PAPER, underline=True, bounds=None, placed=None) -> tuple[float, float, float, float]:
    """Handwritten text on a paper scrap, anchored at its bottom-left. Returns (x, y, width, height) drawn."""
    attrs, s, tw, th = _measure(text, size, max_w)
    if bounds is not None:
        if placed is not None:
            x, y = _place(x, y, tw + 20, th + 18, bounds, placed)
        else:
            x, y = _clamp(x, y, tw + 20, th + 18, bounds[0], bounds[1])
    pad_y = 9
    _draw_paper(x - 10, y - pad_y, tw + 20, th + 2 * pad_y, rnd, color)
    _ink().setStroke()
    s.drawInRect_withAttributes_(((x, y), (max_w, th)), attrs)  # text block exactly centred in the paper
    if underline:
        _stroke([(x + i * (tw / 6), y - 3 + (2 if i % 2 else -2)) for i in range(0, 7)], rnd, 1.0, 1.0)
    return x, y, tw + 20, th + 18


class _SketchView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_SketchView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.scene = None  # Scene with AppKit coords (bottom-left origin)
        self.seed = 1
        self.badge = None  # (text, pulsing) or None: the "listening" indicator
        self.progress = 1.0  # 0..1 reveal of the current scene
        self.stroke_total = 40
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
        _REVEAL["progress"] = self.progress
        _REVEAL["index"] = 0
        _REVEAL["total"] = max(1, self.stroke_total)
        style = self.seed % 4

        placed: list = []
        main_note = None
        if sc.target is not None:
            tx, ty = sc.target
            label = f"{sc.step}. {sc.text}" if sc.step else sc.text
            _, _, lw, lh = _measure(label, 19, 480)
            half_w = (sc.target_box[2] / 2 + 14) if sc.target_box else 48
            half_h = (sc.target_box[3] / 2 + 14) if sc.target_box else 40
            right = tx + half_w + lw + 40 < W
            text_x, text_y = (tx + half_w if right else tx - half_w - lw), ty + half_h
            if sc.target_box:
                placed.append((sc.target_box[0] - 10, sc.target_box[1] - 10, sc.target_box[2] + 20, sc.target_box[3] + 20))
            main_note = _place(*_clamp(text_x, text_y, lw + 20, lh + 18, W, H), lw + 20, lh + 18, (W, H), placed) + (lw + 20, lh + 18, right)
        elif sc.text:
            _, _, lw, lh = _measure(sc.text, 19, 480)
            main_note = _place(W / 2 - lw / 2, H - 110, lw + 20, lh + 18, (W, H), placed) + (lw + 20, lh + 18, True)
        why_rect = None
        if sc.why and main_note:
            _, _, ww, wh = _measure(sc.why, 14, 420)
            why_rect = _place(main_note[0] + 6, main_note[1] - 26 - wh, ww + 20, wh + 18, (W, H), placed)

        # Secondary marks (their labels avoid the papers already placed).
        for m in sc.marks:
            mx, my = m.xy
            bw, bh = (m.box[2], m.box[3]) if m.box else (0, 0)
            if m.shape == "circle":
                if m.box:
                    _circle(mx, my, rnd, bw / 2 + 12, bh / 2 + 10)
                else:
                    _circle(mx, my, rnd, 36, 30) if (style + len(m.text)) % 2 else _rounded_box(mx, my, 76, 56, rnd)
            elif m.shape == "box":
                w, h = (bw + 16 if m.box else (m.size[0] or 160)), (bh + 14 if m.box else (m.size[1] or 60))
                _box(mx - w / 2, my - h / 2, w, h, rnd) if style % 2 else _bracket(mx, my, w, h, rnd)
            elif m.shape == "underline":
                width = bw + 8 if m.box else 140
                base_y = my - (bh / 2 + 4 if m.box else 10)
                _highlight(mx, base_y + 4, width, rnd) if style % 2 else \
                    _stroke([(mx - width / 2 + i * (width / 5), base_y + (2 if i % 2 else -2)) for i in range(0, 6)], rnd, 1.4, 1.2)
            if m.text and ("!" in m.text or "ttention" in m.text or "Pas " in m.text):
                _doodle("asterisk", mx - 48, my + 22, rnd)
            elif m.shape == "arrow" and m.to:
                _arrow(m.xy, m.to, rnd)
            if m.text and m.shape != "arrow":
                # Small label next to the mark, with a short link stroke.
                lx = mx + 50 if mx + 300 < W else mx - 50 - 220
                ly = my + 26
                lx, ly, lw2, lh2 = _note(lx, ly, m.text, rnd, size=15, max_w=320, color=PAPER_SOFT, underline=False, bounds=(W, H), placed=placed)
                _stroke([(mx + (34 if lx > mx else -34), my + 8), (lx + (-4 if lx > mx else lw2 - 24), ly - 2)], rnd, 1.1, 1.0)

        # Main note + circle + arrow, drawn last so they stay on top.
        if main_note:
            nx, ny, w, h, right = main_note
            label = (f"{sc.step}. {sc.text}" if sc.step else sc.text)
            _note(nx, ny, label, rnd)
            if why_rect:
                _note(why_rect[0], why_rect[1], sc.why, rnd, size=14, max_w=420, color=PAPER_SOFT, underline=False)
            if sc.target is not None:
                tx, ty = sc.target
                _frame(tx, ty, rnd, style, box=sc.target_box)
                half_w = (sc.target_box[2] / 2 + 12) if sc.target_box else 46
                _arrow((nx + (6 if right else w - 26), ny - 12), (tx + (half_w if right else -half_w), ty + 10), rnd)
            if sc.doodle:
                _doodle(sc.doodle, nx + w - 4, ny + h + 6, rnd)
        # Remember how many strokes this scene has, so the next frames reveal them in sequence.
        self.stroke_total = max(self.stroke_total, _REVEAL["index"]) if self.progress < 1 else _REVEAL["index"]

    def _draw_badge(self):
        """Status badge in the same draft style as the notes: a small paper scrap, handwritten red text,
        a pencil dot that pulses while listening. Sits ~3 cm above the bottom edge, clear of the Dock."""
        import time

        text, pulsing = self.badge
        bounds = self.bounds()
        rnd = random.Random(11)
        attrs, s, tw, th = _measure(text, 15, 600)
        w, h = tw + 44, th + 14
        x, y = bounds.size.width / 2 - w / 2, 114.0
        saved = (_REVEAL["progress"], _REVEAL["index"], _REVEAL["total"])
        _REVEAL["progress"], _REVEAL["index"], _REVEAL["total"] = 1.0, 0, 10_000
        _draw_paper(x, y, w, h, rnd)
        alpha = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(time.time() * 6)) if pulsing else 0.9
        AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(GRAPHITE[0], GRAPHITE[1], GRAPHITE[2], alpha).setFill()
        AppKit.NSBezierPath.bezierPathWithOvalInRect_(((x + 14, y + h / 2 - 5), (10, 10))).fill()
        _ink().setStroke()
        _circle(x + 19, y + h / 2, rnd, 8, 7)  # a loose pencil ring around the dot
        s.drawInRect_withAttributes_(((x + 36, y + (h - th) / 2), (tw + 4, th)), attrs)  # centred on the paper
        _REVEAL["progress"], _REVEAL["index"], _REVEAL["total"] = saved


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

    def _flip_box(self, box):
        if box is None:
            return None
        x, y, w, h = box
        return (x, self._screen_h - y - h, w, h)

    # ------------------------------------------------------------------ API (any thread)

    def show_scene(self, scene: Scene) -> None:
        self._seed += 1
        flipped = Scene(
            text=scene.text[:110], target=self._flip(scene.target), why=scene.why[:160], step=scene.step,
            marks=[Mark(m.shape, self._flip(m.xy), m.text[:60], m.size, self._flip(m.to), self._flip_box(m.box))
                   for m in scene.marks],
            doodle=scene.doodle, target_box=self._flip_box(scene.target_box),
        )

        def apply() -> None:
            self.view.scene = flipped
            self.view.seed = self._seed
            self.view.progress = 0.0  # drawn progressively by run_until
            self.view.stroke_total = 40
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
            if self.view.progress < 1.0:
                self.view.progress = min(1.0, self.view.progress + 0.08)  # ~0.6 s to draw a scene
                self.view.setNeedsDisplay_(True)
            if self.view.badge is not None and self.view.badge[1]:
                self.view.setNeedsDisplay_(True)  # pulse
            until = Foundation.NSDate.dateWithTimeIntervalSinceNow_(min(interval, 0.04) if self.view.progress < 1 else interval)
            while True:
                event = self.app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                    AppKit.NSEventMaskAny, until, Foundation.NSDefaultRunLoopMode, True)
                if event is None:
                    break
                self.app.sendEvent_(event)
        if hide_at_end:
            self.hide()


AUTONOMY_LABELS = ("Show me", "Help if I'm stuck", "Do it, I watch")


class _MagnetView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_MagnetView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.level = 1
        self.on_change = None
        return self

    def isOpaque(self):
        return False

    def mouseDown_(self, event):
        x = self.convertPoint_fromView_(event.locationInWindow(), None).x
        seg = int(max(0, min(2, (x - 12) / ((self.bounds().size.width - 24) / 3))))
        if seg != self.level:
            self.level = seg
            self.setNeedsDisplay_(True)
            if self.on_change:
                self.on_change(seg)

    def drawRect_(self, rect):
        rnd = random.Random(7)
        b = self.bounds()
        W, H = b.size.width, b.size.height
        _REVEAL["progress"], _REVEAL["index"], _REVEAL["total"] = 1.0, 0, 10_000  # draw everything, no reveal
        _draw_paper(6, 6, W - 12, H - 12, rnd)
        _ink().setStroke()
        # Rail with three notches; the active one gets a scribbled knob.
        y = 22
        _stroke([(16, y), (W - 16, y)], rnd, 1.6, 1.0)
        seg_w = (W - 24) / 3
        for i in range(3):
            cx = 12 + seg_w * (i + 0.5)
            _stroke([(cx, y - 6), (cx, y + 6)], rnd, 1.4, 0.8)
            if i == self.level:
                # Knob: a scribbled, filled dot on the rail.
                AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*GRAPHITE).setFill()
                AppKit.NSBezierPath.bezierPathWithOvalInRect_(((cx - 7, y - 7), (14, 14))).fill()
                for k in range(2):
                    _circle(cx, y, rnd, 11 - k * 2, 10 - k * 2)
        attrs = {AppKit.NSFontAttributeName: _hand_font(13), AppKit.NSForegroundColorAttributeName: _ink()}
        Foundation.NSString.stringWithString_(f"Magnet: {AUTONOMY_LABELS[self.level]}").drawInRect_withAttributes_(
            ((14, H - 40), (W - 28, 28)), attrs)


class MagnetWidget:
    """Clickable autonomy slider, bottom-left. Visible to the user, hidden from screen capture."""

    def __init__(self, level: int, on_change: Callable[[int], None]) -> None:
        w, h = 330.0, 80.0
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((18, 18), (w, h)), AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setLevel_(AppKit.NSScreenSaverWindowLevel)
        self.window.setSharingType_(AppKit.NSWindowSharingNone)
        self.window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorStationary)
        self.view = _MagnetView.alloc().initWithFrame_(((0, 0), (w, h)))
        self.view.level = level
        self.view.on_change = on_change
        self.window.setContentView_(self.view)
        self.window.orderFrontRegardless()
        # Rect in top-left screen points (pynput's frame), to tell Magnet clicks apart from clicks in the app.
        screen_h = AppKit.NSScreen.screens()[0].frame().size.height
        self.rect = (18.0, screen_h - 18.0 - h, w, h)

    def contains(self, x: float, y: float) -> bool:
        rx, ry, rw, rh = self.rect
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def set_level(self, level: int) -> None:
        def apply() -> None:
            self.view.level = level
            self.view.setNeedsDisplay_(True)

        _on_main(apply)

    def close(self) -> None:
        _on_main(lambda: self.window.orderOut_(None))


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
