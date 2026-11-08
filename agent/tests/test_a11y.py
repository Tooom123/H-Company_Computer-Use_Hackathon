"""Matching a step description to browser accessibility elements (pure logic, no macOS calls)."""

from hcs_agent.a11y import Candidate, match


def _el(role, name, x=0, y=0, w=80, h=30):
    return Candidate(role=role, name=name, frame=(x, y, w, h))


CHATTER = [
    _el("AXButton", "Send message", 1000, 270), _el("AXButton", "Log note", 1120, 270),
    _el("AXButton", "Activity", 1230, 270), _el("AXStaticText", "Log note", 300, 600, 60, 16),
    _el("AXTextArea", "Log an internal note...", 1000, 330, 400, 60), _el("AXButton", "Log", 1000, 400, 50, 28),
    _el("AXGroup", "Acme Demo", 0, 150, 1512, 800),  # the whole form, named after the record
]


def test_label_in_description_wins_and_role_hint_prefers_the_button():
    best = match("the Log note button at the top of the chatter panel, between Send message and Activity", CHATTER)[0]
    assert (best.role, best.name) == ("AXButton", "Log note")


def test_sibling_labels_are_told_apart():
    best = match("the Log button just under the internal note composer in the chatter", CHATTER)[0]
    assert (best.role, best.name) == ("AXButton", "Log")


def test_placeholder_names_a_text_box():
    best = match("the 'Log an internal note...' text box in the chatter", CHATTER)[0]
    assert best.role == "AXTextArea"


def test_huge_containers_lose_to_controls():
    els = [_el("AXGroup", "Acme Demo", 0, 150, 1512, 800), _el("AXStaticText", "Acme Demo", 100, 300, 90, 18)]
    best = match("the pipeline card titled Acme Demo", els)[0]
    assert best.role == "AXStaticText"


def test_no_match_returns_empty():
    assert match("the cloud-shaped save icon", CHATTER) == []


def test_sitemap_doc_lookup_and_platform_memory(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from hcs_agent import sitemap

    assert sitemap.find_doc_pages("share a session with my team", k=1)[0]["title"] == "Share a session"
    monkeypatch.setattr(sitemap, "_MEMORY_DIR", tmp_path)
    info = SimpleNamespace(url="https://platform.hcompany.ai/sessions/0123456789ab?x=1", title="Sessions",
                           elements=[Candidate("AXButton", "Create agent", (0, 0, 10, 10)),
                                     Candidate("AXLink", "API keys", (0, 0, 10, 10)),
                                     Candidate("AXStaticText", "some text", (0, 0, 10, 10))])
    sitemap.remember(info)
    sitemap.remember(info)
    pages = sitemap.known_pages("hcompany")
    assert len(pages) == 1 and pages[0].path == "/sessions/<id>" and pages[0].seen == 2
    assert "Create agent" in sitemap.platform_summary("hcompany") and "some text" not in sitemap.platform_summary("hcompany")
    assert "Share a session" in sitemap.context_for("hcompany", "share a session", with_doc=False)


def test_ax_product_identity_without_expected_page_evidence_is_inconclusive():
    from types import SimpleNamespace
    from hcs_agent.a11y import screen_check
    info = SimpleNamespace(app="Chrome", title="Odoo", url="https://demo.odoo.com/", is_front=True,
                           elements=[Candidate("AXButton", "Menu", (0, 0, 20, 20)),
                                     Candidate("AXLink", "Settings", (30, 0, 20, 20))])
    matched, _ = screen_check("expected result", "odoo", info=info)
    assert matched is None
    matched, _ = screen_check("expected result", "salesforce", info=info)
    assert matched is False
