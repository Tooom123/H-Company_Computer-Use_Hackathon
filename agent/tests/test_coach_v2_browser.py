"""Navigation protocol tests; native Chrome behavior still requires a live run."""
import sys
from types import SimpleNamespace

import pytest

from hcs_agent.coach_v2 import CoachProtocolError
from hcs_agent.coach_v2_browser import MacChromeTab, open_documentation_tab


URL = "https://hub.hcompany.ai/agents-api/browser/configuration"
SOURCE = "https://platform.hcompany.ai/agents"


class Browser:
    def __init__(self, ready=True):
        self.calls = []
        self.ready = ready
        self.field = object()

    def open_new_tab(self, check):
        check()
        self.calls.append("new_tab")

    def blank_address_field(self):
        self.calls.append("observe_blank_address")
        return self.field if self.ready else None

    def fill_address(self, field, url):
        assert field is self.field and url == URL
        self.calls.append("fill")

    def submit_address(self, field, url, check):
        assert field is self.field and url == URL
        check()
        self.calls.append("submit")


def test_submission_requires_new_blank_tab_and_address_focus():
    browser = Browser()
    assert open_documentation_tab(URL, SOURCE, ui=browser) is None
    assert browser.calls == ["new_tab", "observe_blank_address", "fill", "submit"]


@pytest.mark.parametrize("url,source", [
    ("https://example.com/", SOURCE), ("https://hub.hcompany.ai.evil.example/", SOURCE),
    (URL, "https://example.com/"), ("https://hub.hcompany.ai/\n", SOURCE),
])
def test_bad_origins_cannot_open_a_tab(url, source):
    browser = Browser()
    with pytest.raises(CoachProtocolError):
        open_documentation_tab(url, source, ui=browser)
    assert browser.calls == []


@pytest.mark.parametrize("stop_after", [0, 1, 2, 3])
def test_cancellation_prevents_each_subsequent_effect(stop_after):
    browser = Browser()
    with pytest.raises(CoachProtocolError, match="cancelled"):
        open_documentation_tab(URL, SOURCE, ui=browser, cancelled=lambda: len(browser.calls) >= stop_after)
    assert "submit" not in browser.calls
    if stop_after < 3:
        assert "fill" not in browser.calls


def test_failed_new_tab_never_types_into_original_page(monkeypatch):
    browser = Browser(ready=False)
    ticks = iter([1., 2.])
    monkeypatch.setattr("hcs_agent.coach_v2_browser.time.monotonic", lambda: next(ticks))
    with pytest.raises(CoachProtocolError, match="couldn't safely focus"):
        open_documentation_tab(URL, SOURCE, ui=browser)
    assert browser.calls == ["new_tab", "observe_blank_address"]


@pytest.mark.parametrize("url,label,value,in_web,ready", [
    ("chrome://newtab/", "Address and search bar", "", False, True),
    ("chrome://new-tab-page/", "Barre d'adresse et de recherche", "", False, True),
    (SOURCE, "Address and search bar", "", False, False),
    ("chrome://newtab/", "Address and search bar", SOURCE, False, False),
    ("chrome://newtab/", "Search sessions", "", False, False),
    ("chrome://newtab/", "Address and search bar", "", True, False),
])
def test_native_focus_guard_rejects_original_tab_page_inputs_and_nonempty_addresses(
        monkeypatch, url, label, value, in_web, ready):
    from hcs_agent import a11y

    browser = MacChromeTab.__new__(MacChromeTab)
    browser.app = object()
    browser.window = object()
    field, parent = object(), object()
    attrs = {
        (browser.app, "AXFocusedUIElement"): field,
        (field, "AXRole"): "AXTextField",
        (field, "AXDescription"): label,
        (field, "AXValue"): value,
        (field, "AXParent"): parent,
        (parent, "AXRole"): "AXWebArea" if in_web else "AXToolbar",
        (parent, "AXParent"): browser.window,
    }
    monkeypatch.setitem(sys.modules, "ApplicationServices", SimpleNamespace(CFEqual=lambda a, b: a is b))
    monkeypatch.setattr(a11y, "_attr", lambda element, attr: attrs.get((element, attr)))
    monkeypatch.setattr(browser, "_front", lambda: None)
    monkeypatch.setattr(browser, "_current_url", lambda: url)
    assert (browser.blank_address_field() is field) is ready


def menu_node(role, title="", children=(), enabled=True):
    return {"AXRole": role, "AXTitle": title, "AXChildren": list(children), "AXEnabled": enabled}


def test_file_lookup_never_traverses_unrelated_large_submenus(monkeypatch):
    from hcs_agent import a11y

    file_menu = menu_node("AXMenuBarItem", "File")
    history = menu_node("AXMenuBarItem", "History", [menu_node("AXMenu", children=[
        menu_node("AXMenuItem", f"Previous page {i}") for i in range(300)])])
    root = menu_node("AXMenuBar", children=[file_menu, history])
    reads = []

    def attr(element, name):
        reads.append((element, name))
        return element.get(name)

    monkeypatch.setattr(a11y, "_attr", attr)
    assert MacChromeTab._menu(root, "AXMenuBarItem", {"File", "Fichier"}) is file_menu
    assert not any(element is history and name == "AXChildren" for element, name in reads)
    assert len(reads) < 15


@pytest.mark.parametrize("title", ["New tab", "New Tab", "NEW TAB", "Nouvel onglet", "NOUVEL ONGLET"])
@pytest.mark.parametrize("wrapped", [False, True])
def test_new_tab_lookup_accepts_live_capitalization_at_native_menu_depth(monkeypatch, title, wrapped):
    from hcs_agent import a11y

    target = menu_node("AXMenuItem", title)
    nested_namesake = menu_node("AXMenuItem", "Other command", [menu_node("AXMenu", children=[
        menu_node("AXMenuItem", "New Tab")])])
    children = [target, nested_namesake]
    root = menu_node("AXMenuBarItem", "File", [menu_node("AXMenu", children=children)] if wrapped else children)
    monkeypatch.setattr(a11y, "_attr", lambda element, name: element.get(name))
    assert MacChromeTab._menu(root, "AXMenuItem", {"New Tab", "Nouvel onglet"}) is target


@pytest.mark.parametrize("children", [
    [menu_node("AXMenuItem", "New tab", enabled=False)],
    [menu_node("AXMenuItem", "New tab", enabled=0)],
    [menu_node("AXMenuItem", "New tab"), menu_node("AXMenuItem", "NEW TAB")],
    [menu_node("AXMenuItem", "New incognito tab")],
])
def test_new_tab_lookup_rejects_disabled_ambiguous_and_other_commands(monkeypatch, children):
    from hcs_agent import a11y

    root = menu_node("AXMenuBarItem", "File", [menu_node("AXMenu", children=children)])
    monkeypatch.setattr(a11y, "_attr", lambda element, name: element.get(name))
    with pytest.raises(CoachProtocolError, match="identify Chrome"):
        MacChromeTab._menu(root, "AXMenuItem", {"New Tab", "Nouvel onglet"})
