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
