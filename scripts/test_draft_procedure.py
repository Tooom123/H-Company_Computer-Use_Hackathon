"""scripts/draft_procedure.py on an offline documentation fixture (no network)."""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import draft_procedure as D  # noqa: E402

PAGE = (Path(__file__).parent / "fixtures" / "odoo_doc_sample.html").read_text()


def test_html_blocks_keep_ui_markup_and_drop_chrome():
    blocks = D.html_to_blocks(PAGE)
    assert any("{{CRM app ‣ Sales ‣ My Pipeline}}" in b for b in blocks)
    assert any("[[Activities]]" in b for b in blocks)
    assert not any("ignored" in b or "Docs menu" in b or "Footer" in b for b in blocks)


def test_steps_follow_the_documentation_order_and_the_acted_control():
    steps = D.extract_steps(D.html_to_blocks(PAGE))
    assert [(s["kind"], s["instruction"]) for s in steps] == [
        ("click", "Clique sur CRM app"), ("click", "Clique sur Sales"), ("click", "Clique sur My Pipeline"),
        ("click", "Clique sur Activities"),            # not "Chatter": the click is on Activities
        ("type", "Renseigne le champ Summary"),
        ("click", "Clique sur Schedule"),
    ]
    assert steps[3]["element"] == "the Activities button"
    assert all(s["done_when"] for s in steps)


def test_markdown_from_linkup_is_parsed_too():
    md = "1. Go to **Settings**.\n2. Click `Save` at the top.\n- Type the name in the **Name** field"
    steps = D.extract_steps(D.markdown_to_blocks(md))
    assert [s["instruction"] for s in steps] == ["Clique sur Settings", "Clique sur Save", "Renseigne le champ Name"]


def test_draft_is_valid_for_the_engine_and_marked_as_draft(tmp_path):
    pytest.importorskip("hcs_agent.procedures", reason="agent package not importable")
    out = tmp_path / "draft.yaml"
    assert D.main(["--file", str(Path(__file__).parent / "fixtures" / "odoo_doc_sample.html"), "--id", "odoo_crm_draft_x",
                   "--title", "Schedule a follow-up", "--objective", "Schedule a To Do on {opportunity}",
                   "-o", str(out)]) == 0
    text = out.read_text()
    assert text.startswith("# DRAFT") and "valid for the engine's Procedure model" in text
    from hcs_agent.procedures import Procedure
    proc = Procedure.model_validate(yaml.safe_load(text))
    assert len(proc.guide_steps) == 6 and proc.guide_steps[3].element == "the Activities button"
