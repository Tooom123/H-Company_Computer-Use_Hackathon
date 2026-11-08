"""Open documentation through native Chrome UI, independent of keyboard layout.

This helper only submits navigation. The runtime must observe the resulting
documentation page before saying it opened; no page-load wait happens here.
"""
from __future__ import annotations

from collections import deque
import time

from .coach_v2 import CoachProtocolError, allowed_docs_url, allowed_page


class MacChromeTab:
    """Bounded AX access to the already focused Chrome window, never page JS."""

    def __init__(self, expected_url):
        from AppKit import NSWorkspace
        import ApplicationServices as AS
        from . import a11y

        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is None or front.bundleIdentifier() not in {"com.google.Chrome", "org.chromium.Chromium"}:
            raise CoachProtocolError("Bring H Platform to the front in Chrome first.")
        self.pid = front.processIdentifier()
        self.app = AS.AXUIElementCreateApplication(self.pid)
        self.window = a11y._attr(self.app, "AXFocusedWindow")
        if self.window is None or self._current_url() != expected_url:
            raise CoachProtocolError("The browser page changed before opening documentation.")

    def _front(self):
        from AppKit import NSWorkspace
        import ApplicationServices as AS
        from . import a11y

        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        window = a11y._attr(self.app, "AXFocusedWindow")
        if (front is None or front.processIdentifier() != self.pid or window is None
                or not AS.CFEqual(window, self.window)):
            raise CoachProtocolError("The browser focus changed; documentation was not submitted.")

    def _current_url(self):
        from . import a11y

        web = a11y._web_area(self.window)
        return str(a11y._attr(web, "AXURL") or "") if web is not None else ""

    @staticmethod
    def _menu(root, role, labels):
        from . import a11y

        wanted = {label.strip().casefold() for label in labels}
        # The menu bar's direct children are its top-level menus. Walking their
        # descendants first can exhaust the bound inside History/Bookmarks before
        # ever visiting File. A File menu exposes items directly or via AXMenu;
        # do not enter other items' submenus and match unrelated nested commands.
        children = a11y._attr(root, "AXChildren") or []
        queue = deque((child, 1) for child in children)
        max_depth = 1 if role == "AXMenuBarItem" else 2
        matches, visited = [], 0
        while queue and visited < 160:
            element, depth = queue.popleft()
            visited += 1
            element_role = a11y._attr(element, "AXRole")
            title = a11y._attr(element, "AXTitle")
            if (element_role == role and isinstance(title, str)
                    and title.strip().casefold() in wanted
                    and a11y._boolean_state(a11y._attr(element, "AXEnabled")) is not False):
                matches.append(element)
            if depth < max_depth and element_role == "AXMenu":
                queue.extend((child, depth + 1) for child in (a11y._attr(element, "AXChildren") or []))
        if queue or len(matches) != 1:
            raise CoachProtocolError("I couldn't identify Chrome's New Tab menu safely.")
        return matches[0]

    def open_new_tab(self, check):
        import ApplicationServices as AS
        from . import a11y

        self._front()
        menu_bar = a11y._attr(self.app, "AXMenuBar")
        if menu_bar is None:
            raise CoachProtocolError("Chrome's menu bar is unavailable.")
        file_menu = self._menu(menu_bar, "AXMenuBarItem", {"File", "Fichier"})
        check()
        if AS.AXUIElementPerformAction(file_menu, "AXPress") != 0:
            raise CoachProtocolError("Chrome's File menu could not be opened.")
        new_tab = self._menu(file_menu, "AXMenuItem", {"New Tab", "Nouvel onglet"})
        check()
        self._front()
        if AS.AXUIElementPerformAction(new_tab, "AXPress") != 0:
            raise CoachProtocolError("Chrome could not open a new tab.")

    def blank_address_field(self):
        import ApplicationServices as AS
        from . import a11y

        self._front()
        # A failed New Tab action must never overwrite the user's H Platform tab.
        if self._current_url() not in {"", "about:blank", "chrome://newtab/", "chrome://new-tab-page/"}:
            return None
        field = a11y._attr(self.app, "AXFocusedUIElement")
        if field is None or a11y._attr(field, "AXRole") not in {"AXTextField", "AXComboBox"}:
            return None
        labels = {a11y._attr(field, attr) for attr in ("AXTitle", "AXDescription", "AXPlaceholderValue")}
        if not labels.intersection({"Address and search bar", "Search or enter web address",
                                    "Barre d'adresse et de recherche", "Barre d’adresse et de recherche"}):
            return None
        if a11y._attr(field, "AXValue") not in {"", None}:
            return None
        ancestor = field
        for _ in range(20):
            if AS.CFEqual(ancestor, self.window):
                return field
            if a11y._attr(ancestor, "AXRole") in {"AXWebArea", "AXSecureTextField"}:
                return None
            ancestor = a11y._attr(ancestor, "AXParent")
            if ancestor is None:
                return None
        return None

    def fill_address(self, field, url):
        import ApplicationServices as AS
        from . import a11y

        self._front()
        focused = a11y._attr(self.app, "AXFocusedUIElement")
        if focused is None or not AS.CFEqual(focused, field):
            raise CoachProtocolError("The new tab's address bar lost focus.")
        if AS.AXUIElementSetAttributeValue(field, "AXValue", url) != 0:
            raise CoachProtocolError("Chrome did not accept the documentation address.")
        if a11y._attr(field, "AXValue") != url:
            raise CoachProtocolError("The documentation address could not be verified.")

    def submit_address(self, field, url, check):
        import ApplicationServices as AS
        import Quartz
        from . import a11y

        self._front()
        focused = a11y._attr(self.app, "AXFocusedUIElement")
        if focused is None or not AS.CFEqual(focused, field) or a11y._attr(field, "AXValue") != url:
            raise CoachProtocolError("The address bar changed before navigation.")
        # Return has the same macOS keycode on AZERTY and QWERTY. Explicit flags
        # avoid inheriting Option/Command from a previous physical recording key.
        check()
        for down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, 0x24, down)
            Quartz.CGEventSetFlags(event, 0)
            Quartz.CGEventPostToPid(self.pid, event)


def open_documentation_tab(url, expected_url, *, cancelled=lambda: False, ui=None):
    """Submit an official URL only after observing a new blank native tab.

    At most 350 ms is spent waiting for Chrome's omnibox focus, with cancellation
    checked every 20 ms. Page loading/redirect checks belong to the runtime loop.
    ``ui`` is a narrow fakeable adapter; production always uses native Chrome AX.
    """
    if not allowed_docs_url(url) or not allowed_page(expected_url):
        raise CoachProtocolError("Only official H documentation can be opened here.")

    def check():
        if cancelled():
            raise CoachProtocolError("Documentation navigation was cancelled.", reason="cancelled")

    check()
    browser = ui if ui is not None else MacChromeTab(expected_url)
    browser.open_new_tab(check)
    deadline = time.monotonic() + .35
    while True:
        check()
        field = browser.blank_address_field()
        if field is not None:
            break
        if time.monotonic() >= deadline:
            raise CoachProtocolError("I opened a new tab but couldn't safely focus its address bar.")
        time.sleep(.02)
    check()
    browser.fill_address(field, url)
    check()
    browser.submit_address(field, url, check)
