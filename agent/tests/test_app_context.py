from types import SimpleNamespace

import pytest

from hcs_agent.a11y import PageInfo
from hcs_agent.app_context import NATIVE_BUNDLE, ProductKnowledge, make_request, profile_for_page, request_matches_page
from hcs_agent.knowledge import DocAnswer, Source
from hcs_agent.procedures import ProcedureRegistry


def browser(url, **kw):
    return PageInfo(app="Google Chrome", title=kw.pop("title", "Observed"), url=url, **kw)


@pytest.mark.parametrize("url,software", [
    ("https://platform.hcompany.ai/agents/sessions/example", "h-company"),
    ("https://hub.hcompany.ai/agents-api/browser/profiles", "h-company"),
    ("https://app.devin.ai/org/example", "cognition"),
    ("https://holo-demo.62.83.79.254.sslip.io/odoo/crm", "odoo"),
    ("http://holo-rich.localhost:18091/odoo/crm", "odoo"),
    ("https://my426318.s4hana.cloud.sap/ui#PurchaseOrder", "sap"),
])
def test_profile_uses_observed_origin(url, software):
    assert profile_for_page(browser(url)).software == software
    assert profile_for_page(browser(url, is_front=False)) is None


@pytest.mark.parametrize("url", [
    "https://platform.hcompany.ai.evil.example/", "https://platform.hcompany.ai@evil.example/",
    "https://user:secret@platform.hcompany.ai/", "https://platform.hcompany.ai:8888/",
    "https://platform.hcompany.ai/auth/signin", "https://platform.hcompany.ai/api-keys",
    "https://holo-demo.62.83.79.254.sslip.io/web/login", "https://other.s4hana.cloud.sap/ui",
    "http://platform.hcompany.ai/", "file:///private/notes", "https://platform.hcompany.ai:bad/",
])
def test_unrecognized_or_private_login_page_cannot_start_a_request(url):
    assert profile_for_page(browser(url)) is None


def test_native_identity_is_not_inferred_from_a_title():
    native = PageInfo(app="Devin", title="", url="", native=True, bundle_id=NATIVE_BUNDLE)
    assert profile_for_page(native).surface == "native"
    native.bundle_id = "com.other.app"
    assert profile_for_page(native) is None
    assert profile_for_page(browser("https://example.org", title="Devin")) is None


class Corpus:
    def __init__(self, product):
        self.product, self.calls = product, []

    def ask(self, query, software=None, depth=None):
        self.calls.append((query, software))
        return DocAnswer(query=query, answer=self.product + " documentation",
                         sources=[Source(name=self.product, url="knowledge://demo-" + self.product + "/doc/revision#chunk-0")])


def test_product_change_isolates_docs_goal_and_history():
    corpora = {s: Corpus(s) for s in ("cognition", "odoo", "sap", "h-company")}
    knowledge = ProductKnowledge(corpora)
    devin, _ = make_request("Show the last command", browser("https://app.devin.ai/session/123"), knowledge)
    odoo, status = make_request("Like in Devin, show me this purchase order", browser(
        "https://holo-demo.62.83.79.254.sslip.io/odoo/purchase"), knowledge, devin)
    assert odoo.goal == "Like in Devin, show me this purchase order"
    assert odoo.software == "odoo"
    assert odoo.parameters["previous_goal"] == ""
    assert "odoo documentation" in odoo.parameters["doc_context"]
    assert "cognition documentation" not in odoo.parameters["doc_context"]
    assert status["software"] == "odoo" and status["sources"] == 1
    assert "réception" in corpora["odoo"].calls[0][0]
    assert corpora["sap"].calls == []
    next_request, _ = make_request("What remains to receive?", browser(
        "https://holo-demo.62.83.79.254.sslip.io/odoo/purchase"), knowledge, odoo)
    assert next_request.parameters["previous_goal"] == odoo.goal
    assert request_matches_page(odoo, browser("https://app.devin.ai/")) is False
    assert knowledge.ask("anything", software="unknown") is None


def test_native_surface_does_not_reuse_browser_history_or_scope():
    knowledge = ProductKnowledge({"cognition": Corpus("cognition")})
    web, _ = make_request("Show session", browser("https://app.devin.ai/"), knowledge)
    native = PageInfo(app="Devin", title="", url="", native=True, bundle_id=NATIVE_BUNDLE)
    request, _ = make_request("Show commands", native, knowledge, web)
    assert request.parameters["previous_goal"] == ""
    assert request_matches_page(request, browser("https://app.devin.ai/")) is False
    procedure = ProcedureRegistry().for_request(request)
    assert "focused native application" in procedure.preconditions[0]
    assert "Response language: English" in procedure.agent_instructions
    assert any("placing orders" in rule for rule in procedure.forbidden_actions)


def test_missing_docs_do_not_claim_retrieval_or_block_supported_app():
    def fail(*a, **k):
        raise RuntimeError("missing corpus")
    request, status = make_request("Help me", browser("https://app.devin.ai/"), SimpleNamespace(ask=fail))
    assert not request.parameters["doc_context"]
    assert status["sources"] == 0


def test_retrieved_json_and_user_braces_are_literal_not_procedure_templates():
    answer = DocAnswer(query="help", answer='{"excerpts": [{"text": "use {field}"}]}')
    request, _ = make_request("Explain {field}", browser("https://app.devin.ai/"),
                              SimpleNamespace(ask=lambda *a, **k: answer))
    bound = ProcedureRegistry().for_request(request).bound(request)
    assert answer.answer in bound.guide_instructions
    assert bound.objective == "Explain {field}"
    assert "{field}" in bound.checks['goal_achieved']


def test_browser_reader_does_not_walk_unrelated_or_login_content(monkeypatch):
    from hcs_agent import a11y
    monkeypatch.setattr(a11y, '_web_area', lambda _: 'web')
    monkeypatch.setattr(a11y, '_attr', lambda _, attr: 'https://unrelated.example/login' if attr == 'AXURL' else 'Login')
    monkeypatch.setattr(a11y, '_frame', lambda _: (0, 0, 1000, 800))
    monkeypatch.setattr(a11y, '_walk', lambda _: pytest.fail('Must reject the origin before reading its content'))
    page = a11y._read_browser_page(('window', 'Google Chrome', True), known_only=True)
    assert page.elements == []


@pytest.mark.parametrize('observation', [None, browser('https://app.devin.ai/')])
def test_running_odoo_guide_blocks_on_missing_or_changed_app(monkeypatch, tmp_path, observation):
    from hcs_agent.backend import MockBackend
    from hcs_agent.runner import Intervention
    monkeypatch.delenv('HCS_AX_NATIVE_BUNDLE_ID', raising=False)
    request, _ = make_request('Show the order', browser(
        'https://holo-demo.62.83.79.254.sslip.io/odoo/purchase'), ProductKnowledge({}))
    backend = MockBackend()
    backend.page_catalogue = lambda bound: None if observation is None else (observation, [])
    backend.plan_step = lambda *a: pytest.fail('Wrong product must never reach the planner')
    it = Intervention(request, backend, ProcedureRegistry(), lambda _: None, tmp_path)
    it._on_guidance_nowait = lambda _: None
    bound = ProcedureRegistry().for_request(request).bound(request)
    result = it._dynamic_guide(bound)
    # The planner loop is exercised directly so no simulated verifier can invent a success.
    if result is None:
        pytest.fail('Expected an explicit blocked result from the planner loop')
    assert result.declared.outcome == 'blocked'
