"""Browser or explicitly selected native accessibility tree as the primary element finder.

Chrome and the explicitly selected Devin Desktop application expose controls through the macOS
accessibility API: role, label, placeholder and the exact rectangle on screen. Input values are never read. Reading it takes
milliseconds and is pixel-exact, so it is the first thing we try when a guide step needs "the Log note button"
or "the Opportunity's Name field". Holo (grounding.py) stays as the fallback for what the tree cannot name
(icons without labels, canvas) and as the tie-breaker when several elements share a label.

Requires the Accessibility permission for the process that runs the agent (same as the kill switch).
Chrome populates the web content tree once a client asks for it (`AXManualAccessibility` / `AXEnhancedUserInterface`).
Coordinates are screen points with a top-left origin (the same frame as pynput and the overlay scenes).
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field

BROWSERS = ("Google Chrome", "Chromium", "Brave Browser", "Arc", "Microsoft Edge")
# Explicit native selection, never inferred from a window title or an arbitrary app name.
NATIVE_APPLICATIONS = {"com.exafunction.windsurf": "Devin Desktop"}

# role words in a description -> accessibility roles that fit
ROLE_HINTS: dict[str, tuple[str, ...]] = {
    "button": ("AXButton", "AXPopUpButton", "AXMenuButton"),
    "link": ("AXLink",),
    "field": ("AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"),
    "input": ("AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"),
    "box": ("AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"),
    "editor": ("AXTextArea", "AXTextField"),
    "search": ("AXTextField", "AXSearchField", "AXComboBox"),
    "tab": ("AXRadioButton", "AXTab", "AXButton", "AXLink"),
    "menu": ("AXMenuItem", "AXMenuButton", "AXPopUpButton", "AXButton", "AXLink"),
    "entry": ("AXLink", "AXMenuItem", "AXButton", "AXStaticText"),
    "checkbox": ("AXCheckBox",),
    "option": ("AXMenuItem", "AXStaticText", "AXLink", "AXButton"),
    "header": ("AXHeading", "AXStaticText", "AXColumnHeader"),
    "heading": ("AXHeading", "AXStaticText"),
    "title": ("AXHeading", "AXStaticText", "AXTextField"),
    "card": ("AXStaticText", "AXLink", "AXGroup", "AXHeading"),
    "icon": ("AXButton", "AXImage", "AXLink"),
    "logo": ("AXImage", "AXLink", "AXButton"),
    "stage": ("AXButton", "AXRadioButton", "AXStaticText", "AXLink"),
    "column": ("AXHeading", "AXStaticText"),
}
INTERACTIVE = ("AXButton", "AXLink", "AXTextField", "AXTextArea", "AXComboBox", "AXCheckBox", "AXRadioButton",
               "AXPopUpButton", "AXMenuItem", "AXTab", "AXSearchField", "AXMenuButton")
INPUT_ROLES = frozenset({"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXSecureTextField"})
STOPWORDS = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "with", "and", "or", "its", "this", "that",
             "top", "bottom", "left", "right", "under", "below", "above", "next", "between", "near", "inside",
             "page", "panel", "form", "view", "bar", "area", "section", "list", "dialog", "row", "line", "second",
             "first", "small", "large", "purple", "colored", "coloured", "just", "then", "placeholder", "titled",
             "named", "called", "labelled", "labeled", "showing", "shows", "which", "opened", "open", "active",
             "new", "existing"} | set(ROLE_HINTS)


@dataclass
class Candidate:
    role: str
    name: str
    frame: tuple[float, float, float, float]  # x, y, w, h — screen points, top-left origin
    score: float = 0.0
    why: str = ""
    ref: object = None  # the AXUIElement, for hit-testing
    enabled: bool | None = None  # None means the accessibility API did not provide a Boolean state.
    selected: bool | None = None

    @property
    def center(self) -> tuple[int, int]:
        x, y, w, h = self.frame
        return int(x + w / 2), int(y + h / 2)

    @property
    def box(self) -> tuple[int, int, int, int]:
        x, y, w, h = self.frame
        return int(x), int(y), int(w), int(h)


@dataclass
class PageInfo:
    app: str
    title: str
    url: str
    is_front: bool = True  # the browser is the frontmost application
    viewport: tuple[float, float, float, float] | None = None  # web area frame (screen points)
    elements: list[Candidate] = field(default_factory=list)
    walk_s: float = 0.0
    native: bool = False
    bundle_id: str | None = None


def available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import ApplicationServices as AS

        return bool(AS.AXIsProcessTrusted())
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- low level


def _attr(el, name):
    import ApplicationServices as AS

    err, val = AS.AXUIElementCopyAttributeValue(el, name, None)
    return val if err == 0 else None


def _frame(el):
    import ApplicationServices as AS

    v = _attr(el, "AXFrame")
    if v is None:
        return None
    ok, r = AS.AXValueGetValue(v, AS.kAXValueTypeCGRect, None)
    if not ok:
        return None
    return (float(r.origin.x), float(r.origin.y), float(r.size.width), float(r.size.height))


def _text(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _boolean_state(value) -> bool | None:
    """Only explicit Boolean/bridged 0-or-1 states are evidence; AX errors are unknown."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def _browsers():
    """Running supported browsers as (pid, name, is_frontmost), frontmost first."""
    from AppKit import NSWorkspace

    ws = NSWorkspace.sharedWorkspace()
    front = ws.frontmostApplication()
    front_pid = front.processIdentifier() if front is not None else -1
    out = []
    for app in ws.runningApplications():
        name = app.localizedName() or ""
        if name in BROWSERS:
            out.append((app.processIdentifier(), name, app.processIdentifier() == front_pid))
    out.sort(key=lambda t: not t[2])
    return out


def _browser_window():
    """The focused (or first) window of a browser, frontmost browser preferred: (window, app name, is_front)."""
    import ApplicationServices as AS

    for pid, name, is_front in _browsers():
        app = AS.AXUIElementCreateApplication(pid)
        for flag in ("AXManualAccessibility", "AXEnhancedUserInterface"):
            AS.AXUIElementSetAttributeValue(app, flag, True)  # ask Chrome to expose the web content
        win = _attr(app, "AXFocusedWindow")
        if win is None:
            wins = _attr(app, "AXWindows") or []
            win = wins[0] if wins else None
        if win is not None:
            return win, name, is_front
    return None


def native_target() -> str:
    """An explicitly configured target; an unknown value must still disable browser fallback."""
    return os.environ.get("HCS_AX_NATIVE_BUNDLE_ID", "").strip()


def _native_window(bundle: str):
    """Only the focused window of the exact foreground application, without enumerating other apps."""
    if bundle not in NATIVE_APPLICATIONS:
        return None
    import ApplicationServices as AS
    from AppKit import NSWorkspace

    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is None or front.bundleIdentifier() != bundle:
        return None
    pid = front.processIdentifier()
    app = AS.AXUIElementCreateApplication(pid)
    for flag in ("AXManualAccessibility", "AXEnhancedUserInterface"):
        AS.AXUIElementSetAttributeValue(app, flag, True)
    win = _attr(app, "AXFocusedWindow")
    return (win, NATIVE_APPLICATIONS[bundle], pid) if win is not None else None


def _native_page(bundle: str) -> PageInfo:
    unavailable = PageInfo(app=NATIVE_APPLICATIONS.get(bundle, "Native application"), title="", url="",
                           is_front=False, native=True, bundle_id=bundle)
    selected = _native_window(bundle)
    if selected is None:
        return unavailable
    win, name, pid = selected
    started = time.monotonic()
    web = _web_area(win)
    # AXURL is an observed URL, not a conversion of a native identity to a guessed website.
    url = str(_attr(web, "AXURL") or "") if web is not None else ""
    # Electron's native menus can be siblings of AXWebArea in the focused window.
    # Walking only the web area misses an opened popup and keeps suggesting its trigger.
    # Stay inside this exact focused window; never enumerate application/background windows.
    viewport = _frame(win) or (_frame(web) if web is not None else None)
    elements = [e for e in _walk(win) if e.role not in {"AXWindow", "AXWebArea"}]
    if viewport:
        x, y, w, h = viewport
        elements = [e for e in elements if e.frame[0] + e.frame[2] > x and e.frame[0] < x + w
                    and e.frame[1] + e.frame[3] > y and e.frame[1] < y + h]
    # A focus/window switch during collection invalidates the entire observation.
    again = _native_window(bundle)
    if again is None or again[2] != pid:
        return unavailable
    import ApplicationServices as AS
    same_window = getattr(AS, "CFEqual", lambda a, b: a is b)(win, again[0])
    if not same_window:
        return unavailable
    return PageInfo(app=name, title=_text(_attr(win, "AXTitle")), url=url, is_front=True,
                    native=True, bundle_id=bundle, viewport=viewport, elements=elements,
                    walk_s=time.monotonic() - started)


def _web_area(win):
    stack = [win]
    seen = 0
    while stack and seen < 400:
        el = stack.pop()
        seen += 1
        role = _attr(el, "AXRole")
        if role == "AXWebArea":
            return el
        if role not in INPUT_ROLES:
            stack.extend(_attr(el, "AXChildren") or [])
    return None


def _walk(web, max_nodes: int = 6000) -> list[Candidate]:
    """Every element with a name and an on-screen frame. One IPC per node (multiple attributes at once)."""
    import ApplicationServices as AS

    attrs = ["AXRole", "AXTitle", "AXDescription", "AXPlaceholderValue", "AXChildren", "AXFrame",
             "AXEnabled", "AXSelected"]
    out: list[Candidate] = []
    stack = [web]
    count = 0
    while stack and count < max_nodes:
        el = stack.pop()
        count += 1
        err, vals = AS.AXUIElementCopyMultipleAttributeValues(el, attrs, 0, None)
        if err != 0 or vals is None:
            continue
        role, title, desc, placeholder, children, frame_v, enabled, selected = vals
        role = role if isinstance(role, str) else ""
        # Electron editors expose typed values as AXStaticText descendants as well as AXValue.
        # Preserve only the input's own label/placeholder; never walk into its content subtree.
        if role not in INPUT_ROLES and children is not None and not isinstance(children, (str, int, float)):
            try:
                stack.extend(list(children))  # NSArray proxy, not a Python list
            except TypeError:
                pass
        name = _text(title) or _text(desc) or _text(placeholder)
        # Page text (static text, headings, link/button captions) may name an element; what the user typed
        # into a field never does: field values are not read (they can hold personal data or secrets).
        if not name and role in ("AXStaticText", "AXHeading", "AXLink", "AXButton"):
            name = _text(_attr(el, "AXValue"))
        if not name or len(name) > 120:
            continue
        frame = None
        if frame_v is not None and not isinstance(frame_v, (str, int, float)):
            ok, r = AS.AXValueGetValue(frame_v, AS.kAXValueTypeCGRect, None)
            if ok:
                frame = (float(r.origin.x), float(r.origin.y), float(r.size.width), float(r.size.height))
        if frame is None or frame[2] < 2 or frame[3] < 2:
            continue
        # Disabled/selected controls remain useful evidence in the page catalogue.
        # Selection does not imply either disabled state or a successful action.
        out.append(Candidate(role=role, name=name, frame=frame, ref=el,
                             enabled=_boolean_state(enabled), selected=_boolean_state(selected)))
    return out


def visible_at_point(cand: Candidate, depth: int = 10) -> bool:
    """Hit-test the candidate's centre: is it (or one of its descendants) what the user would actually click?
    False when a menu, dialog or another window covers it. Unknown element -> True (do not over-filter)."""
    import ApplicationServices as AS

    if cand.ref is None:
        return True
    x, y = cand.center
    system = AS.AXUIElementCreateSystemWide()
    err, hit = AS.AXUIElementCopyElementAtPosition(system, float(x), float(y), None)
    if err != 0 or hit is None:
        return True
    el = hit
    for _ in range(depth):
        if el is None:
            break
        try:
            if AS.CFEqual(el, cand.ref):
                return True
        except Exception:  # noqa: BLE001
            return True
        el = _attr(el, "AXParent")
    # Not the candidate: covered only if what we hit belongs to a menu, dialog, popover or another window.
    # (Hit-testing has quirks on nested web content; without such evidence, trust the candidate.)
    el = hit
    covering = {"AXMenu", "AXMenuBar", "AXSheet", "AXPopover", "AXDialog", "AXMenuItem", "AXPopUpButton"}
    for _ in range(8):
        if el is None:
            break
        role = _attr(el, "AXRole") or ""
        sub = _attr(el, "AXSubrole") or ""
        if role in covering or sub in ("AXDialog", "AXSystemDialog", "AXApplicationDialog", "AXModal"):
            return False
        if role == "AXWindow":
            try:
                win = _attr(cand.ref, "AXWindow")
                return win is not None and bool(AS.CFEqual(el, win))  # another window covers it
            except Exception:  # noqa: BLE001
                return True
        el = _attr(el, "AXParent")
    return True


# --------------------------------------------------------------------------- public API


def page() -> PageInfo | None:
    """What the frontmost browser shows: app, window title, URL and the named elements with their frames."""
    if not available():
        return None
    if bundle := native_target():
        return _native_page(bundle)
    t0 = time.time()
    bw = _browser_window()
    if bw is None:
        return None
    win, app_name, is_front = bw
    web = _web_area(win)
    if web is None:
        return PageInfo(app=app_name, title=_text(_attr(win, "AXTitle")), url="", is_front=is_front)
    url = _attr(web, "AXURL")
    url = str(url) if url is not None else ""
    info = PageInfo(app=app_name, title=_text(_attr(win, "AXTitle")), url=url, is_front=is_front, viewport=_frame(web))
    elements = _walk(web)
    # Right after a navigation Chrome exposes the new page progressively: give it a moment before deciding
    # the page is empty (an empty catalogue would send the guide to the slow path for nothing).
    for _ in range(4):
        loading = _attr(web, "AXLoadingProgress")
        busy = isinstance(loading, (int, float)) and loading < 1.0
        if len(elements) > 3 and not busy:
            break
        time.sleep(0.25)
        elements = _walk(web)
        url = str(_attr(web, "AXURL") or url)
        info.url, info.title = url, _text(_attr(win, "AXTitle"))
    if info.viewport:  # keep what is actually visible in the viewport (scrolled-out elements keep a frame)
        vx, vy, vw, vh = info.viewport
        elements = [e for e in elements
                    if e.frame[0] + e.frame[2] > vx and e.frame[0] < vx + vw and e.frame[1] + e.frame[3] > vy
                    and e.frame[1] < vy + vh]
    info.elements = elements
    info.walk_s = time.time() - t0
    return info


def warm_up(rounds: int = 3) -> int:
    """Chrome exposes the web content only after a client starts asking: poke it a few times at startup.
    Returns the number of named elements seen last (0 = no browser page available)."""
    seen = 0
    for _ in range(rounds):
        info = page()
        seen = len(info.elements) if info else 0
        if seen > 1:
            break
        time.sleep(0.4)
    return seen


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t not in STOPWORDS and len(t) > 1]


def _quoted(description: str) -> list[str]:
    """Labels the author put in quotes or capitalised: « Log note », "Opportunity's Name", Acme Demo."""
    out = re.findall(r"[\"'«“]([^\"'»”]{2,60})[\"'»”]", description)
    out += re.findall(r"\b([A-Z][\w']+(?: [A-Z][\w']+)*)\b", description)
    return [o.strip() for o in out if o.strip()]


def match(description: str, elements: list[Candidate]) -> list[Candidate]:
    """Rank the page's elements against a natural-language description of one control.

    Scoring: an element whose name appears verbatim in the description (or vice-versa) scores by the length of
    that name; the role hinted by the description ("button", "field"...) adds a bonus; interactive roles
    beat plain text; placeholders count as names. Returns candidates sorted best first (score > 0 only).
    """
    desc_l = description.lower()
    d_tokens = set(_tokens(description))
    wanted_roles: set[str] = set()
    for word, roles in ROLE_HINTS.items():
        if re.search(rf"\b{word}s?\b", desc_l):
            wanted_roles.update(roles)
    quoted = [q.lower() for q in _quoted(description)]
    # Labels after these words describe neighbours, not the target ("between Send message and Activity").
    ctx_match = re.search(r"\b(between|next to|left of|right of|under|below|above|near|beside|after|before|"
                          r"opposite|not |instead of|rather than)\b", desc_l)
    ctx_start = ctx_match.start() if ctx_match else len(desc_l)
    role_words = "|".join(ROLE_HINTS)
    ranked: list[Candidate] = []
    for el in elements:
        n = el.name.lower()
        score = 0.0
        why = ""
        if n in desc_l and len(n) >= 2:
            pos = desc_l.find(n)
            score = 10 + min(len(n), 24)  # the element's own label is written in the description
            why = f"label '{el.name}' in description"
            if pos >= ctx_start:
                score -= 12  # named as a neighbour / what NOT to click
                why += " (as context)"
            else:
                score += 6 * (1 - pos / max(1, len(desc_l)))  # the subject comes first
            if re.search(re.escape(n) + r"'?s?\s+(?:" + role_words + r")s?\b", desc_l):
                score += 8  # "Log note button": label directly followed by its role word
                why += " + role word"
        elif any(q and (q in n or n in q) and min(len(q), len(n)) >= 3 for q in quoted):
            q = next(q for q in quoted if q and (q in n or n in q))
            score = 8 + min(len(q), len(n))
            why = f"label '{el.name}' ~ '{q}'"
        else:
            e_tokens = set(_tokens(el.name))
            common = d_tokens & e_tokens
            if common and len(common) >= max(1, len(e_tokens) // 2):
                score = 2 + 2 * len(common)
                why = f"words {sorted(common)}"
        if score <= 0:
            continue
        if wanted_roles:
            if el.role in wanted_roles:
                score += 6
            elif el.role in INTERACTIVE:
                score += 1
            else:
                score -= 3
        elif el.role in INTERACTIVE:
            score += 2
        # a huge element (the whole page, a big container) is rarely the control
        if el.frame[2] * el.frame[3] > 400 * 300:
            score -= 4
        ranked.append(Candidate(el.role, el.name, el.frame, score, why, el.ref))
    ranked.sort(key=lambda c: (-c.score, c.frame[1], c.frame[0]))
    return ranked


def find(description: str, info: PageInfo | None = None) -> tuple[Candidate | None, list[Candidate], PageInfo | None]:
    """Best candidate for the description on the current page, plus the runner-ups (for tie-breaking)."""
    info = info or page()
    if info is None or not info.is_front or not info.elements:
        return None, [], info
    ranked = match(description, info.elements)
    if not ranked:
        return None, [], info
    # Drop candidates hidden under a menu, a dialog or another window (hit-test, ~1 ms each; top 6 only).
    top = ranked[:6]
    visible = [c for c in top if visible_at_point(c)]
    if not visible:
        return None, [], info  # the control exists but something covers it: let Holo / the diagnosis speak
    best = visible[0]
    ties = [c for c in visible[1:] if c.score >= best.score - 1.0]
    return best, ties, info


def page_text(info: PageInfo | None = None) -> str:
    info = info or page()
    return " \n".join(e.name for e in info.elements) if info else ""


def screen_check(expected: str, software: str = "", info: PageInfo | None = None) -> tuple[bool | None, str]:
    """Instant screen check from the tree: (True/False/None = cannot tell, what is visible).

    True when the browser is in front, its URL or title names the software, and most of the capitalised words
    of the expected description (e.g. New, Qualified, Pipeline) appear in the page. False when the browser is
    not in front or the software is not in the URL/title. None when the page is unknown to us.
    """
    info = info or page()
    if info is None or len(info.elements) <= 1:
        return None, ""
    where = f"{info.app}: {info.title[:60]} ({info.url[:60]})"
    if not info.is_front:
        return False, f"{where} — not in front"
    sw = (software or "").lower()
    if getattr(info, "native", False):
        if getattr(info, "bundle_id", None) not in NATIVE_APPLICATIONS or sw not in ("", "cognition", "devin"):
            return False, where
        hay = f"{info.app} {info.title} cognition devin".lower()
    else:
        hay = f"{info.url} {info.title}".lower()
    if sw and sw not in hay and sw.rstrip("y") not in hay:  # "hcompany" vs "hcompany.ai", "odoo" vs "odoo.com"
        return False, where
    words = [w for w in re.findall(r"\b[A-Z][\w']+\b", expected) if w.lower() not in {sw, "crm", "the", "a", "h"}]
    if not words:
        return None, where  # product identity alone does not prove the expected page or outcome
    text = page_text(info).lower()
    hits = sum(1 for w in words if w.lower() in text)
    if hits >= max(1, round(0.5 * len(words))):
        return True, where
    # Right software, but the words that name the expected page are not there: cannot tell from the tree
    # (labels may differ from the description) -> let the vision check decide instead of saying no.
    return None, where
