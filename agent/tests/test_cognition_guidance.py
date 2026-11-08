"""Offline free-form sponsor coaching, language policy and AX-path regression tests."""

import argparse
import json
from types import SimpleNamespace

import pytest

from hcs_agent import cli
from hcs_agent.backend import HBackend, MockBackend
from hcs_agent.contract import Mode
from hcs_agent.desktop_feedback import DesktopFeedback, RunJournal
from hcs_agent.procedures import ProcedureRegistry, RESPONSE_LANGUAGE_INSTRUCTIONS, coaching_page_allowed
from hcs_agent.runner import Intervention


@pytest.mark.parametrize("software", ["hcompany", "cognition", "devin"])
def test_free_question_and_context_remain_verbatim_under_english_response_policy(software):
    question = '  Explique {"status":"Completed"} sans rien modifier. Réponds en français.  '
    context = "Previous request: pourquoi ce résultat ?\nLast guidance: read the status."
    req = cli._coaching_request(question, software, context)
    bound = ProcedureRegistry().for_request(req).bound(req)
    assert req.goal == req.parameters["question"] == question
    assert bound.objective == question and question in bound.guide_instructions
    assert context == req.parameters["context"] and context in bound.guide_instructions
    assert RESPONSE_LANGUAGE_INSTRUCTIONS in bound.guide_instructions
    assert "Speak French" not in bound.guide_instructions
    assert bound.guide_script() == [] and req.mode is Mode.guide and req.autonomy == 0
    if software in {"cognition", "devin"}:
        assert req.software == "cognition" and req.procedure_id == "cognition_general_guide"
        assert "Odoo" not in bound.objective
        assert "app.devin.ai" in bound.agent_instructions


def test_cognition_journal_is_separate_from_h_and_has_no_implied_feedback(tmp_path):
    req = cli._coaching_request("Où est la réponse de Devin ?", "cognition")
    journal = RunJournal(tmp_path, req, lambda _: None, simulated=True)
    meta = json.loads((journal.directory / "episode.json").read_text())
    assert meta["scenario_id"] == "COGNITION-LIVE" and meta["source"] == "cognition"
    assert meta["simulated"] and not (journal.directory / "labels.json").exists()


def test_agent_and_verifier_specs_keep_english_policy_without_touching_user_request(monkeypatch):
    backend = object.__new__(HBackend)
    backend.model, backend.screenshot_max_width = "offline", 1024
    backend.observe_only = True
    monkeypatch.setattr(backend, "_desktop_channel", lambda: "offline-channel")
    for name in ("guide-cognition", "verify-h"):
        spec = backend._agent_spec(name, "User question: Explique-moi cette page.")
        assert "Explique-moi cette page." in spec["instructions"]
        assert RESPONSE_LANGUAGE_INSTRUCTIONS in spec["instructions"]
        assert "Never click" in spec["instructions"]


def test_cognition_talk_bypasses_odoo_router_and_preserves_followup(tmp_path, monkeypatch):
    from hcs_agent import voice
    texts = iter(["Explique cette session Devin.", "Continue mais explique le bouton {question}."])
    vocabularies, requests = [], []

    class PTT:
        key_name = "ctrl+shift+h"
        def __init__(self, **kw):
            vocabularies.append(kw["vocabulary"])
            self.transcripts = SimpleNamespace(empty=lambda: True)
        def start(self):
            pass
        def stop(self):
            pass
        def wait_transcript(self, **kw):
            try:
                return next(texts)
            except StopIteration:
                raise KeyboardInterrupt

    monkeypatch.setattr(voice, "PushToTalk", PTT)
    monkeypatch.setattr(voice, "IntentRouter", lambda _: pytest.fail("Sponsor questions must bypass the Odoo router"))
    monkeypatch.setattr(cli, "make_backend", lambda _: SimpleNamespace())
    monkeypatch.setattr(cli, "_start_control", lambda *args: None)
    monkeypatch.setitem(cli._SPEECH, "speaker", None)
    monkeypatch.setitem(cli._MAGNET, "widget", None)
    monkeypatch.setitem(cli._MAGNET, "current", None)
    monkeypatch.setattr(cli, "_FEEDBACK", DesktopFeedback())

    def execute(req, *args, **kwargs):
        requests.append(req)
        monkeypatch.setitem(cli._MAGNET, "current", SimpleNamespace(guidance=[SimpleNamespace(instruction="Read the session status.")],
                                                                  state=SimpleNamespace(terminal=True)))
        return 0

    monkeypatch.setattr(cli, "_execute", execute)
    args = argparse.Namespace(software="cognition", no_overlay=True, mock=True, runs_dir=str(tmp_path),
                              key="ctrl+shift+h", confirm=False, once=False)
    assert cli.cmd_talk(args) == 0
    assert len(requests) == 2 and all(r.software == "cognition" for r in requests)
    assert requests[1].goal == "Continue mais explique le bouton {question}."  # not replaced by the previous request
    assert "Explique cette session Devin." in requests[1].parameters["context"]
    assert "Read the session status." in requests[1].parameters["context"]
    assert "Devin" in vocabularies[0] and "Odoo" not in vocabularies[0]


@pytest.mark.parametrize("software,url,allowed", [
    ("cognition", "https://app.devin.ai/sessions/demo", True),
    ("cognition", "https://docs.devin.ai/api-reference/keys", True),
    ("cognition", "https://cognition.com/blog/swe-2-flash", True),
    ("cognition", "https://www.cognition.com/", True),
    ("cognition", "https://cognition.com.evil.test/", False),
    ("cognition", "https://app.devin.ai:444/sessions/demo", False),
    ("cognition", "https://app.devin.ai/settings/api-keys", False),
    ("cognition", "https://app.devin.ai/login", False),
    ("cognition", "https://app.devin.ai.evil.test/sessions/demo", False),
    ("cognition", "https://platform.hcompany.ai/sessions/demo", False),
    ("h-company", "https://platform.hcompany.ai/settings/vaults", False),
    ("h-company", "https://hub.hcompany.ai/agents-api/vaults/overview", True),
    ("h-company", "https://platform.hcompany.ai/%61pi-keys", False),
])
def test_sponsor_ax_scope_checks_origin_and_sensitive_account_routes(software, url, allowed):
    assert coaching_page_allowed(software, url) is allowed


@pytest.fixture
def dynamic(tmp_path, monkeypatch):
    req = cli._coaching_request("Explique cette session.", "cognition", "Previous guidance: open the session.")
    backend = MockBackend()
    it = Intervention(req, backend, ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    bound = ProcedureRegistry().for_request(req).bound(req)
    shown, planner_calls = [], []
    info = SimpleNamespace(is_front=True, title="Demo session", url="https://app.devin.ai/sessions/demo?private=query")
    control = SimpleNamespace(role="AXButton", name="Details", center=(100, 100), box=(80, 80, 40, 40))
    backend.page_catalogue = lambda _: (info, [control])
    plans = iter([{"done": False, "instruction": "Open Details", "kind": "click", "target": 0},
                  {"done": True, "summary": "The session status is visible; code correctness remains unverified."}])
    backend.plan_step = lambda *args: planner_calls.append(args) or next(plans)
    monkeypatch.setattr(it, "_on_guidance", lambda step: shown.append(step) or (True, "Observed interaction: click. Result not verified."))
    monkeypatch.setattr(it, "_wait_page_change", lambda *args: None)
    monkeypatch.setattr("hcs_agent.overlay.screen_size_points", lambda: (1470, 956))
    return SimpleNamespace(it=it, bound=bound, backend=backend, info=info, shown=shown, calls=planner_calls)


def test_dynamic_ax_guidance_keeps_scope_language_context_and_observation_provenance(dynamic):
    r = dynamic
    result = r.it._dynamic_guide(r.bound)
    assert result.declared.outcome == "done"
    assert r.shown[0].box_exact and r.shown[-1].last and r.shown[-1].kind == "info"
    assert "correctness remains unverified" in r.shown[-1].instruction
    assert RESPONSE_LANGUAGE_INSTRUCTIONS in r.calls[0][1]
    assert "Previous guidance: open the session." in r.calls[0][1]
    assert "Do not send a question to Devin" in r.calls[0][1]
    assert "private=query" not in r.calls[0][2]
    assert "Observed interaction:" in r.calls[1][4][0] and "(user:" not in r.calls[1][4][0]


def test_dynamic_ax_restricted_page_blocks_before_planner_or_h_fallback(dynamic):
    dynamic.info.url = "https://app.devin.ai/settings/api-keys"
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result is not None and result.declared.outcome == "blocked"
    assert dynamic.calls == [] and dynamic.shown[-1].last
    assert dynamic.shown[-1].pointer is None


def test_dynamic_ax_invalid_planner_target_never_indexes_wrong_control(dynamic):
    dynamic.backend.plan_step = lambda *args: {"done": False, "instruction": "Please clarify the intended control.",
                                             "kind": "info", "target": -1}
    dynamic.it._dynamic_guide(dynamic.bound, max_steps=1)
    assert dynamic.shown[0].pointer is None and dynamic.shown[0].box is None


def test_dynamic_ax_uses_public_cognition_documentation_once_without_private_query(dynamic):
    from hcs_agent.knowledge import DocAnswer, Source
    lookups = []

    def ask(query, **kwargs):
        lookups.append((query, kwargs))
        return DocAnswer(query=query, answer="PUBLIC_CORPUS: session reviews distinguish tests from deployment.",
                         sources=[Source(name="Devin docs", url="https://docs.devin.ai/")])

    dynamic.backend.knowledge = SimpleNamespace(ask=ask)
    dynamic.it._dynamic_guide(dynamic.bound)
    assert len(lookups) == 1 and lookups[0][1]["software"] == "cognition"
    assert dynamic.bound.request.goal not in lookups[0][0]
    assert "PUBLIC_CORPUS" in dynamic.calls[0][1]
    assert dynamic.it.knowledge[-1].purpose == "agent_lookup"


def test_dynamic_ax_rejects_unrelated_or_spoofed_documentation(dynamic):
    from hcs_agent.knowledge import DocAnswer, Source
    dynamic.backend.knowledge = SimpleNamespace(ask=lambda *args, **kwargs: DocAnswer(
        query="Public docs", answer="WRONG_VENDOR_CORPUS", sources=[Source(name="Fake docs", url="https://docs.devin.ai.evil.test/")]))
    dynamic.it._dynamic_guide(dynamic.bound)
    assert "WRONG_VENDOR_CORPUS" not in dynamic.calls[0][1]
    assert dynamic.it.knowledge == []


@pytest.mark.parametrize("tenant,software,uri_tenant,suffix,allowed", [
    ("cognition-human", "cognition", "cognition-human", "", True),
    ("cognition-human", "h-company", "cognition-human", "", False),
    ("cognition-human", "cognition", "other-tenant", "", False),
    ("cognition-human", "cognition", "attacker@cognition-human", "", False),
    ("cognition-human", "cognition", "cognition-human:443", "", False),
    ("cognition-human", "cognition", "cognition-human", "?secret=value", False),
])
def test_dynamic_ax_accepts_only_versioned_local_corpus_for_exact_tenant_and_software(
        dynamic, tenant, software, uri_tenant, suffix, allowed):
    from hcs_agent.knowledge import DocAnswer, Source
    uri = f"knowledge://{uri_tenant}/devin-docs/{'a' * 64}{suffix}#chunk-0"
    dynamic.backend.knowledge = SimpleNamespace(tenant_id=tenant, software=software,
        ask=lambda *args, **kwargs: DocAnswer(query="Public docs", answer="LOCAL_CORPUS_CONTENT",
                                             sources=[Source(name="Versioned docs", url=uri)]))
    dynamic.it._dynamic_guide(dynamic.bound)
    assert ("LOCAL_CORPUS_CONTENT" in dynamic.calls[0][1]) is allowed
    if allowed:
        assert uri in dynamic.calls[0][1]
        assert "untrusted reference data" in dynamic.calls[0][1]
        assert dynamic.it.knowledge[-1].sources[0].url == uri
    else:
        assert dynamic.it.knowledge == []


@pytest.mark.parametrize('software,url,bundle,front,allowed', [
    ('cognition', '', 'com.exafunction.windsurf', True, True),
    ('cognition', 'vscode-file://vscode-app/local/private/path', 'com.exafunction.windsurf', True, True),
    ('cognition', 'https://app.devin.ai/sessions/demo', 'com.exafunction.windsurf', True, True),
    ('cognition', 'https://app.devin.ai/login', 'com.exafunction.windsurf', True, False),
    ('cognition', 'https://attacker.test/', 'com.exafunction.windsurf', True, False),
    ('cognition', '', 'com.exafunction.windsurf.spoof', True, False),
    ('cognition', '', 'com.exafunction.windsurf', False, False),
    ('h-company', '', 'com.exafunction.windsurf', True, False),
])
def test_native_coaching_scope_uses_explicit_bundle_without_inventing_a_url(software, url, bundle, front, allowed):
    assert coaching_page_allowed(software, url, native=True, bundle_id=bundle, is_front=front) is allowed


def _make_native(dynamic, monkeypatch):
    monkeypatch.setenv('HCS_AX_NATIVE_BUNDLE_ID', 'com.exafunction.windsurf')
    dynamic.info.native = True
    dynamic.info.bundle_id = 'com.exafunction.windsurf'
    dynamic.info.url = 'vscode-file://vscode-app/local/private/resource'
    dynamic.info.viewport = (0, 0, 1000, 700)


def test_native_planner_receives_native_identity_not_internal_resource_path(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert 'Native application: Devin Desktop' in dynamic.calls[0][2]
    assert 'com.exafunction.windsurf' in dynamic.calls[0][2]
    assert 'vscode-file' not in dynamic.calls[0][2]
    assert '/private/resource' not in dynamic.calls[0][2]
    assert dynamic.shown[0].box == (80, 80, 40, 40)


def test_native_empty_tree_explains_blocker_without_planner(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.backend.page_catalogue = lambda _: (dynamic.info, [])
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked'
    assert dynamic.calls == []
    assert 'accessibility controls are unavailable' in dynamic.shown[0].instruction


def test_native_focus_switch_while_planning_discards_arrow_and_answer(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    control = SimpleNamespace(role='AXButton', name='Review', center=(100, 100), box=(80, 80, 40, 40))
    background = SimpleNamespace(**vars(dynamic.info))
    background.is_front = False
    views = iter([(dynamic.info, [control]), (background, [])])
    dynamic.backend.page_catalogue = lambda _: next(views)
    result = dynamic.it._dynamic_guide(dynamic.bound, max_steps=1)
    assert result.declared.outcome == 'unclear'
    assert dynamic.shown == []  # Neither a stale arrow nor an answer is presented.


def test_native_backend_never_captures_desktop_or_uses_agents_fallback(monkeypatch, tmp_path):
    import threading
    from hcs_agent import a11y
    monkeypatch.setenv('HCS_AX_NATIVE_BUNDLE_ID', 'com.exafunction.windsurf')
    backend = object.__new__(HBackend)
    backend.observe_only = True
    monkeypatch.setattr(backend, '_tree_locate', lambda _: (None, []))
    monkeypatch.setattr(backend, '_grounding', lambda: pytest.fail('Native AX mode must not capture the desktop'))
    assert backend.locate('Missing button').found is False
    assert backend.effect_visible('Success') == (False, '')
    assert backend.screenshot(tmp_path / 'capture.png') is None
    req = cli._coaching_request('Explain the visible window', 'cognition')
    bound = ProcedureRegistry().for_request(req).bound(req)
    result = backend.run_guidance(bound, 'Explain', lambda _: None, lambda _: None, threading.Event())
    assert result.declared.outcome == 'blocked' and result.h_session_id is None
    assert not (tmp_path / 'capture.png').exists()


def test_native_unavailable_catalogue_is_not_reclassified_as_browser_fallback(monkeypatch):
    from hcs_agent import a11y
    backend = object.__new__(HBackend)
    backend.observe_only, backend.use_a11y = True, True
    unavailable = a11y.PageInfo('Devin Desktop', '', '', native=True,
                               bundle_id='com.exafunction.windsurf', is_front=False)
    monkeypatch.setattr(a11y, 'page', lambda: unavailable)
    monkeypatch.setattr(a11y, 'visible_at_point', lambda _: pytest.fail('No foreign app hit test'))
    assert backend.page_catalogue() == (unavailable, [])


def test_native_runner_missing_ax_finishes_blocked_without_any_h_agent(tmp_path, monkeypatch):
    from hcs_agent.contract import ApproveCommand, CaseStatus
    monkeypatch.setenv('HCS_AX_NATIVE_BUNDLE_ID', 'com.exafunction.windsurf')
    monkeypatch.setenv('HCS_GUIDE_OBSERVE_ONLY', '1')
    backend = MockBackend(step_delay_s=0)
    backend.page_catalogue = lambda *args: None
    backend.run_guidance = lambda *args: pytest.fail('Native missing AX fell back to an Agents session')
    backend.run_attempt = lambda *args: pytest.fail('Native missing AX started an actor')
    backend.verify = lambda *args: pytest.fail('Native missing AX started a verifier')
    backend.screenshot = lambda *args: None
    request = cli._coaching_request('Explain the native Review panel', 'cognition')
    events = []
    runner = Intervention(request, backend, ProcedureRegistry(), events.append, tmp_path, uplink=False)
    runner.start()
    runner.approve(ApproveCommand())
    runner.wait(3)
    assert runner.report is not None and runner.report.status is CaseStatus.escalated
    assert runner.report.declared.outcome == 'blocked'
    assert not runner.takeover
    assert any(e.type == 'guidance' and 'Native accessibility guidance is unavailable' in (e.message or '') for e in events)
