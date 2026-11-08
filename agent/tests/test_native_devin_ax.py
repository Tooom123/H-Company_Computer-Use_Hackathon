"""Native Devin AX boundaries using fake frameworks only; never inspect the Mac."""

import sys
from types import SimpleNamespace

import pytest

from hcs_agent import a11y


BUNDLE = "test.allowed.devin"


def test_page_info_retains_browser_defaults_for_existing_callers():
    info = a11y.PageInfo("Chrome", "Documentation", "https://docs.devin.ai/")

    assert info.native is False
    assert info.bundle_id is None


def _rect(x=40, y=60, width=900, height=650):
    return SimpleNamespace(
        origin=SimpleNamespace(x=x, y=y),
        size=SimpleNamespace(width=width, height=height),
    )


def _node(role, title="", children=(), **attrs):
    return {
        "AXRole": role, "AXTitle": title, "AXChildren": list(children),
        "AXFrame": _rect(), **attrs,
    }


def _application(bundle=BUNDLE, name="Devin", pid=71):
    return SimpleNamespace(
        bundleIdentifier=lambda: bundle,
        localizedName=lambda: name,
        processIdentifier=lambda: pid,
    )


@pytest.fixture
def fake_ax(monkeypatch):
    """Every framework entry used by the collector resolves to in-memory objects."""
    state = SimpleNamespace(
        front=_application(), root={}, reads=[], created=[], flags=[],
        running_calls=0,
    )

    def running_apps():
        state.running_calls += 1
        raise AssertionError("Native targeting must not enumerate background apps")

    workspace = SimpleNamespace(
        frontmostApplication=lambda: state.front,
        runningApplications=running_apps,
    )
    monkeypatch.setitem(sys.modules, "AppKit", SimpleNamespace(
        NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: workspace),
    ))

    def copy_attribute(node, name, _out):
        state.reads.append((node, name))
        return (0, node[name]) if name in node else (-25205, None)

    def copy_multiple(node, names, _flags, _out):
        state.reads.extend((node, name) for name in names)
        return 0, [node.get(name) for name in names]

    def create_application(pid):
        state.created.append(pid)
        return state.root

    monkeypatch.setitem(sys.modules, "ApplicationServices", SimpleNamespace(
        AXIsProcessTrusted=lambda: True,
        AXUIElementCreateApplication=create_application,
        AXUIElementCopyAttributeValue=copy_attribute,
        AXUIElementCopyMultipleAttributeValues=copy_multiple,
        AXUIElementSetAttributeValue=lambda node, flag, value: (
            state.flags.append((node, flag, value)) or 0
        ),
        AXValueGetValue=lambda value, _type, _out: (True, value),
        kAXValueTypeCGRect=3,
    ))
    monkeypatch.setattr(a11y, "available", lambda: True)
    monkeypatch.setattr(a11y, "NATIVE_APPLICATIONS", {BUNDLE: "Devin"})
    monkeypatch.setattr(a11y.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("HCS_AX_NATIVE_BUNDLE_ID", BUNDLE)

    def browser_forbidden():
        raise AssertionError("Native selection must never fall back to a browser")

    monkeypatch.setattr(a11y, "_browser_window", browser_forbidden)
    return state


def test_native_frontmost_web_area_uses_observed_frame_and_no_invented_url(fake_ax):
    button = _node("AXButton", "Ask", AXFrame=_rect(110, 140, 80, 28))
    offscreen = _node("AXButton", "Outside", AXFrame=_rect(1800, 140, 80, 28))
    web = _node("AXWebArea", children=[button, offscreen], AXLoadingProgress=1.0)
    window = _node("AXWindow", "Sandbox project", [web])
    fake_ax.root = {"AXFocusedWindow": window}

    info = a11y.page()

    assert info is not None
    assert (info.app, info.native, info.bundle_id, info.is_front) == (
        "Devin", True, BUNDLE, True,
    )
    assert info.title == "Sandbox project"
    assert info.url == ""  # A native app identity is not evidence of a website URL.
    assert info.viewport == (40.0, 60.0, 900.0, 650.0)
    assert [(el.name, el.box) for el in info.elements] == [("Ask", (110, 140, 80, 28))]
    assert fake_ax.created == [71, 71]  # Initial capture and foreground/window recheck.
    assert fake_ax.running_calls == 0


def test_native_window_without_web_area_exposes_its_native_controls(fake_ax):
    button = _node("AXButton", "Review", AXFrame=_rect(120, 180, 100, 30))
    window = _node("AXWindow", "Devin", [button])
    fake_ax.root = {"AXFocusedWindow": window}

    info = a11y.page()

    assert info is not None and info.native and info.is_front
    assert info.url == ""
    assert any(el.name == "Review" and el.box == (120, 180, 100, 30) for el in info.elements)


@pytest.mark.parametrize("attributes,enabled,selected", [
    ({}, None, None),
    ({"AXEnabled": False, "AXSelected": True}, False, True),
    ({"AXEnabled": True, "AXSelected": False}, True, False),
    ({"AXEnabled": 0, "AXSelected": 1}, False, True),
    ({"AXEnabled": "false", "AXSelected": -25205}, None, None),
    ({"AXEnabled": object(), "AXSelected": None}, None, None),
])
def test_native_control_states_are_explicit_or_unknown_and_disabled_controls_remain_visible(
        fake_ax, attributes, enabled, selected):
    button = _node("AXButton", "Current plan", AXFrame=_rect(120, 180, 100, 30), **attributes)
    fake_ax.root = {"AXFocusedWindow": _node("AXWindow", "Devin", [button])}

    info = a11y.page()

    control = next(el for el in info.elements if el.name == "Current plan")
    assert control.enabled is enabled
    assert control.selected is selected
    assert (button, "AXEnabled") in fake_ax.reads and (button, "AXSelected") in fake_ax.reads


def test_input_states_do_not_read_entered_values_or_descendants(fake_ax):
    private_child = _node("AXStaticText", AXValue="private-child-text")
    field = _node("AXTextField", "Search", [private_child], AXEnabled=False, AXSelected=True,
                  AXValue="private-field-value", AXFrame=_rect(120, 180, 100, 30))
    fake_ax.root = {"AXFocusedWindow": _node("AXWindow", "Devin", [field])}

    info = a11y.page()

    control = next(el for el in info.elements if el.name == "Search")
    assert control.enabled is False and control.selected is True
    assert not any(node is field and name == "AXValue" for node, name in fake_ax.reads)
    assert not any(node is private_child for node, _name in fake_ax.reads)
    assert not any("private-" in el.name for el in info.elements)


def test_native_menu_sibling_of_web_area_is_collected_without_reading_other_windows_or_input_values(fake_ax):
    trigger = _node("AXPopUpButton", "Devin Settings", AXFrame=_rect(800, 90, 40, 25))
    web = _node("AXWebArea", children=[trigger], AXFrame=_rect(50, 90, 880, 610),
                AXURL="vscode-file://vscode-app/local/workbench.html")
    option = _node("AXMenuItem", "Docs", AXFrame=_rect(700, 120, 180, 25))
    private_child = _node("AXStaticText", AXValue="private-entered-text")
    field = _node("AXTextField", "Search settings", children=[private_child],
                  AXValue="private-field-value", AXFrame=_rect(700, 150, 180, 25))
    menu = _node("AXMenu", children=[option, field], AXFrame=_rect(690, 115, 200, 100))
    window = _node("AXWindow", "Devin", [web, menu], AXFrame=_rect(40, 60, 900, 650))
    unrelated = _node("AXWindow", "Private background", [_node("AXButton", "Do not read")])
    fake_ax.root = {"AXFocusedWindow": window, "AXWindows": [unrelated, window]}

    info = a11y.page()

    assert info.is_front and info.native
    assert info.url == "vscode-file://vscode-app/local/workbench.html"
    assert info.viewport == (40, 60, 900, 650)  # Native window, not the smaller web viewport.
    assert any(el.name == "Docs" and el.box == (700, 120, 180, 25) for el in info.elements)
    assert any(el.name == "Devin Settings" for el in info.elements)
    assert any(el.name == "Search settings" for el in info.elements)
    assert not any(node is unrelated or node is private_child for node, _name in fake_ax.reads)
    assert not any(node is field and name == "AXValue" for node, name in fake_ax.reads)
    assert not any(name == "AXWindows" for _node_read, name in fake_ax.reads)
    assert not any("private-" in el.name or "Do not read" == el.name for el in info.elements)


def test_closing_native_popup_removes_menu_items_from_next_catalogue(fake_ax):
    web = _node("AXWebArea", children=[_node("AXPopUpButton", "Settings")])
    menu = _node("AXMenu", children=[_node("AXMenuItem", "Docs")])
    window = _node("AXWindow", "Devin", [web, menu])
    fake_ax.root = {"AXFocusedWindow": window}
    assert any(el.name == "Docs" for el in a11y.page().elements)

    window["AXChildren"] = [web]

    assert all(el.name != "Docs" for el in a11y.page().elements)


@pytest.mark.parametrize("front", [
    None,
    _application("com.google.Chrome", "Google Chrome", 12),
    _application("test.impostor", "Devin", 13),
    _application(BUNDLE + ".other", "Devin", 14),
])
def test_explicit_native_target_absent_or_not_front_never_reads_other_apps(fake_ax, front):
    fake_ax.front = front

    info = a11y.page()

    assert info is not None
    assert (info.app, info.native, info.bundle_id, info.is_front) == (
        "Devin", True, BUNDLE, False,
    )
    assert info.url == "" and info.elements == []
    assert fake_ax.created == [] and fake_ax.reads == []
    assert fake_ax.running_calls == 0


def test_native_target_only_reads_the_focused_window(fake_ax):
    focused = _node("AXWindow", "Focused", [_node("AXButton", "Ask")])
    background = _node("AXWindow", "Unrelated private window", [_node("AXButton", "Private")])
    fake_ax.root = {"AXFocusedWindow": focused, "AXWindows": [background, focused]}

    info = a11y.page()

    assert info is not None and info.title == "Focused"
    assert all(node is not background for node, _name in fake_ax.reads)
    assert all(name != "AXWindows" for _node_read, name in fake_ax.reads)
    assert all(el.name != "Private" for el in info.elements)


def test_native_target_without_focused_window_does_not_read_another_window(fake_ax):
    background = _node("AXWindow", "Unrelated", [_node("AXButton", "Private")])
    fake_ax.root = {"AXWindows": [background]}

    info = a11y.page()

    assert info is not None and info.native and not info.is_front
    assert info.elements == []
    assert all(name != "AXWindows" for _node_read, name in fake_ax.reads)


@pytest.mark.parametrize("changed", ["application", "process", "window"])
def test_focus_change_during_walk_discards_the_whole_observation(fake_ax, monkeypatch, changed):
    window = _node("AXWindow", "Original", [_node("AXButton", "Ask")])
    fake_ax.root = {"AXFocusedWindow": window}
    original_walk = a11y._walk

    def walk_then_change_focus(root):
        elements = original_walk(root)
        if changed == "application":
            fake_ax.front = _application("com.google.Chrome", "Google Chrome", 12)
        elif changed == "process":
            fake_ax.front = _application(pid=72)
        else:
            fake_ax.root = {"AXFocusedWindow": _node("AXWindow", "Another window")}
        return elements

    monkeypatch.setattr(a11y, "_walk", walk_then_change_focus)

    info = a11y.page()

    assert info is not None and info.native and not info.is_front
    assert info.elements == [] and info.title == "" and info.url == ""
    assert all(pid != 12 for pid in fake_ax.created)


def test_unset_native_target_keeps_the_existing_browser_collector(fake_ax, monkeypatch):
    monkeypatch.delenv("HCS_AX_NATIVE_BUNDLE_ID")
    web = _node("AXWebArea", children=[_node("AXButton", "Ask")],
                AXURL="https://docs.devin.ai/", AXLoadingProgress=1.0)
    window = _node("AXWindow", "Documentation", [web])
    monkeypatch.setattr(a11y, "_browser_window", lambda: (window, "Google Chrome", True))

    info = a11y.page()

    assert info is not None and not info.native and info.bundle_id is None
    assert info.url == "https://docs.devin.ai/"
    assert info.is_front and any(el.name == "Ask" for el in info.elements)


@pytest.mark.parametrize("bundle", ["test.impostor", BUNDLE + ".other", "*"])
def test_unallowlisted_forced_bundle_is_rejected_without_reading_any_app(fake_ax, monkeypatch, bundle):
    monkeypatch.setenv("HCS_AX_NATIVE_BUNDLE_ID", bundle)
    fake_ax.front = _application(bundle)

    try:
        info = a11y.page()
    except ValueError:
        info = None

    assert info is None or (not info.is_front and info.elements == [])
    assert fake_ax.created == [] and fake_ax.reads == []


def test_walk_never_requests_values_from_input_or_password_controls(fake_ax):
    fields = [
        _node(role, "Field label", AXValue="private-field-value")
        for role in ("AXTextField", "AXTextArea", "AXComboBox", "AXSearchField", "AXSecureTextField")
    ]
    fields.append(_node("AXTextField", "Password", AXSubrole="AXSecureTextField", AXValue="private-password"))
    static = _node("AXStaticText", AXValue="Visible explanation")
    web = _node("AXWebArea", children=[*fields, static])

    elements = a11y._walk(web)

    assert any(el.name == "Visible explanation" for el in elements)
    assert not any("private-" in el.name for el in elements)
    assert not any(name == "AXValue" and any(node is field for field in fields)
                   for node, name in fake_ax.reads)
    assert any(node is static and name == "AXValue" for node, name in fake_ax.reads)


def test_long_page_response_is_kept_as_bounded_text_instead_of_disappearing(fake_ax):
    response = "The agent produced an answer. " * 120
    text = _node("AXStaticText", AXValue=response)
    secret = _node("AXStaticText", AXValue="private-editor-content")
    editor = _node("AXTextArea", "Message", [secret])
    items = a11y._walk(_node("AXWebArea", children=[text, editor]))
    paragraph = next(e for e in items if e.role == "AXStaticText")
    assert paragraph.name.startswith("The agent produced an answer.")
    assert "excerpt truncated" in paragraph.name and len(paragraph.name) < 2100
    assert all(node is not secret for node, _ in fake_ax.reads)


@pytest.mark.parametrize("role", [
    "AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXSecureTextField",
])
def test_walk_does_not_read_static_text_descendants_of_inputs(fake_ax, role):
    secret = _node("AXStaticText", AXValue="private-descendant-value")
    field = _node(role, "Visible field label", [secret])
    web = _node("AXWebArea", children=[field])

    elements = a11y._walk(web)

    assert [(el.role, el.name) for el in elements] == [(role, "Visible field label")]
    assert all(node is not secret for node, _attribute in fake_ax.reads)


def test_no_accessibility_permission_means_no_native_reads(fake_ax, monkeypatch):
    monkeypatch.setattr(a11y, "available", lambda: False)

    assert a11y.page() is None
    assert fake_ax.created == [] and fake_ax.reads == []


def test_native_product_identity_alone_is_not_page_evidence(fake_ax):
    info = a11y.PageInfo(
        "Devin", "Sandbox", "", native=True, bundle_id=BUNDLE,
        elements=[a11y.Candidate("AXButton", "Ask", (40, 80, 60, 20)),
                  a11y.Candidate("AXButton", "Review", (40, 110, 60, 20))],
    )

    assert a11y.screen_check("expected result", "cognition", info)[0] is None
    assert a11y.screen_check("Repository details", "cognition", info)[0] is None
    assert a11y.screen_check("Review", "cognition", info)[0] is True
    assert a11y.screen_check("Review", "odoo", info)[0] is False


def test_native_verification_rejects_unknown_identity_despite_matching_title(fake_ax):
    info = a11y.PageInfo(
        "Devin", "Review", "", native=True, bundle_id="test.impostor",
        elements=[a11y.Candidate("AXButton", "Ask", (40, 80, 60, 20)),
                  a11y.Candidate("AXButton", "Review", (40, 110, 60, 20))],
    )

    assert a11y.screen_check("Review", "cognition", info)[0] is False
