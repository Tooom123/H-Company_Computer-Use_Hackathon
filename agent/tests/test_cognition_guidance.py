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
    assert 'not exposed usable controls yet' in dynamic.shown[0].instruction
    assert sum('native catalogue empty' in s.summary for s in dynamic.it.steps) == 3
    assert 'permission' not in dynamic.shown[0].instruction.lower()


def test_native_initial_empty_reads_recover_before_showing_a_blocker(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    info, items = dynamic.backend.page_catalogue(None)
    reads = []

    def catalogue(_):
        reads.append(True)
        return info, [] if len(reads) <= 2 else items

    dynamic.backend.page_catalogue = catalogue
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert len(dynamic.calls) == 2  # Empty reads do not trigger extra model calls.
    assert [step.instruction for step in dynamic.shown] == [
        'Open Details', 'The session status is visible; code correctness remains unverified.']
    assert sum('native catalogue empty' in s.summary for s in dynamic.it.steps) == 2


def test_native_covered_controls_explain_occlusion_not_missing_permission(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.backend.page_catalogue = lambda _: (dynamic.info, [])
    dynamic.backend.last_catalogue_diagnostic = {'status': 'controls_covered', 'covered': 12}
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked' and not dynamic.calls
    assert 'covered' in dynamic.shown[0].instruction
    assert 'permission' not in dynamic.shown[0].instruction.lower()


def test_stop_during_empty_native_retry_prevents_planning(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.backend.page_catalogue = lambda _: (dynamic.info, [])
    monkeypatch.setattr(dynamic.it._stop, 'wait', lambda _: dynamic.it._stop.set())
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.status == 'interrupted' and result.declared.outcome == 'not_run'
    assert not dynamic.calls and not dynamic.shown


def test_native_retry_rechecks_allowed_page_before_planning(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    restricted = SimpleNamespace(**vars(dynamic.info))
    restricted.url = 'https://app.devin.ai/login'
    views = iter([(dynamic.info, []), (restricted, [])])
    dynamic.backend.page_catalogue = lambda _: next(views)
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked' and not dynamic.calls
    assert 'outside the authorized' in result.declared.blocker


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


def test_timing_includes_model_and_both_reads_even_for_discarded_plan(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    control = SimpleNamespace(role='AXButton', name='Review', center=(100, 100), box=(80, 80, 40, 40))
    background = SimpleNamespace(**vars(dynamic.info))
    background.is_front = False
    views = iter([(dynamic.info, [control]), (background, [])])
    clock = [100.0]

    def catalogue(_):
        clock[0] += 0.2
        return next(views)

    def planner(*args):
        clock[0] += 1.5
        return {'instruction': 'Open Review', 'kind': 'click', 'target': 0}

    monkeypatch.setattr('hcs_agent.runner.time.perf_counter', lambda: clock[0])
    dynamic.backend.page_catalogue, dynamic.backend.plan_step = catalogue, planner
    events = []
    monkeypatch.setattr(dynamic.it, '_on_step', events.append)
    dynamic.it._dynamic_guide(dynamic.bound, max_steps=1)
    timing = next(s.detail for s in events if s.detail.get('phase') == 'guidance_preparation')
    assert timing['disposition'] == 'discarded_stale'
    assert timing['timing_ms'] == {'catalogue_ms': 200.0, 'planner_ms': 1500.0,
                                  'fresh_catalogue_ms': 200.0, 'total_ms': 1900.0}
    assert not dynamic.shown


def test_unrelated_layout_change_keeps_one_model_call_and_the_correct_target(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    target = SimpleNamespace(role='AXButton', name='Details', center=(100, 100), box=(80, 80, 40, 40))
    other = SimpleNamespace(role='AXButton', name='Help', center=(250, 100), box=(230, 80, 40, 40))
    moved = SimpleNamespace(role='AXButton', name='Help', center=(252, 100), box=(232, 80, 40, 40))
    views = iter([(dynamic.info, [target, other]), (dynamic.info, [moved, target])])
    dynamic.backend.page_catalogue = lambda _: next(views)
    monkeypatch.setattr(dynamic.it, '_on_guidance', lambda step: dynamic.shown.append(step))
    dynamic.it._dynamic_guide(dynamic.bound, max_steps=1)
    assert len(dynamic.calls) == 1 and len(dynamic.shown) == 1
    assert dynamic.shown[0].where == 'Details' and dynamic.shown[0].box == target.box


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
    assert any(e.type == 'guidance' and "couldn't read Devin's controls" in (e.message or '') for e in events)


def test_native_repeated_plan_reports_no_progress_not_accessibility_failure(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    calls = []
    dynamic.backend.plan_step = lambda *args: calls.append(args) or {
        'done': False, 'instruction': 'Open Details', 'kind': 'click', 'target': 0}
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert len(calls) == 3 and len(dynamic.shown) == 2
    assert result.declared.outcome == 'blocked'
    assert 'same step without confirming progress' in result.declared.blocker
    assert 'accessibility' not in result.declared.blocker.lower()
    assert dynamic.shown[-1].last and dynamic.shown[-1].pointer is None
    assert any('repeated_planner_instruction' in step.summary for step in dynamic.it.steps)
    assert any('Observed interaction:' in note for note in result.declared.steps_taken)
    assert any('Instruction NOT shown:' in note for note in result.declared.steps_taken)


def test_opened_menu_choices_reach_next_plan_and_finish_without_an_extra_click(dynamic, monkeypatch):
    """Regression for a detected click followed by another instruction to open the same menu."""
    from hcs_agent.a11y import Candidate

    _make_native(dynamic, monkeypatch)
    trigger = Candidate('AXPopUpButton', 'Text style', (100, 100, 60, 25))
    choices = [Candidate('AXMenuItem', 'Regular', (100, 130, 150, 25)),
               Candidate('AXMenuItem', 'Bold', (100, 155, 150, 25))]
    items = [trigger]
    dynamic.backend.page_catalogue = lambda _: (dynamic.info, list(items))
    pages = []

    def plan(goal, context, page, candidates, history):
        pages.append(page)
        if len(pages) == 1:
            assert 'Menu options visible now' not in page
            return {'instruction': 'Open Text style', 'kind': 'click', 'target': 0}
        assert 'Menu options visible now' in page
        assert '2. Regular' in page and '3. Bold' in page
        assert any('Observed interaction:' in entry for entry in history)
        return {'done': True, 'kind': 'info', 'target': None,
                'summary': 'The visible styles are Regular and Bold.'}

    def human_click(step):
        dynamic.shown.append(step)
        if not step.last:
            items.extend(choices)
        return True, 'Observed interaction: click inside suggested target. Result not verified.'

    dynamic.backend.plan_step = plan
    dynamic.it._on_guidance = human_click
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert len(dynamic.shown) == 2
    assert dynamic.shown[0].where == 'Text style'
    assert dynamic.shown[1].kind == 'info' and dynamic.shown[1].last
    assert dynamic.shown[1].pointer is None and dynamic.shown[1].box is None
    assert len(result.declared.steps_taken) == 1  # Listing options is not a second human click.


def test_visible_menu_is_context_not_automatic_task_success(dynamic):
    from hcs_agent.a11y import Candidate

    dynamic.backend.page_catalogue = lambda _: (
        dynamic.info, [Candidate('AXMenuItem', 'Regular', (100, 130, 150, 25))])
    dynamic.backend.plan_step = lambda *args: {'done': False, 'kind': 'info',
        'instruction': 'The requested option is not visible.', 'target': None}
    result = dynamic.it._dynamic_guide(dynamic.bound, max_steps=1)
    assert result.declared.outcome == 'unclear'
    assert not dynamic.shown[0].last


def test_repeated_next_instruction_on_changed_pages_is_not_a_stall(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    plans = iter([{'done': False, 'instruction': 'Click Next', 'kind': 'click', 'target': 0}] * 3 +
                 [{'done': True, 'summary': 'The final page is visible.'}])
    dynamic.backend.plan_step = lambda *args: next(plans)

    def advance(step):
        dynamic.shown.append(step)
        dynamic.info.title = f'Wizard page {len(dynamic.shown) + 1}'
        return True, 'Observed interaction; next page is visible.'

    dynamic.it._on_guidance = advance
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert len(dynamic.shown) == 4
    assert not any('repeated_planner_instruction' in step.summary for step in dynamic.it.steps)


def test_explicit_planner_blocker_finishes_without_waiting_for_a_click_or_claiming_success(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    dynamic.it._on_guidance = lambda step: pytest.fail('A terminal blocker must not wait for a user click')
    dynamic.backend.plan_step = lambda *args: {
        'done': True, 'blocked': True, 'kind': 'click', 'target': 0,
        'summary': 'This native pilot cannot guide billing in the web app.'}
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked'
    assert result.declared.blocker == dynamic.shown[-1].instruction
    assert dynamic.shown[-1].last and dynamic.shown[-1].kind == 'info'
    assert dynamic.shown[-1].pointer is None


@pytest.mark.parametrize('plan', [None, {}, {'instruction': '', 'why': 'private-provider-error-details'}])
def test_native_planning_failure_is_distinct_from_readable_tree(dynamic, monkeypatch, plan):
    _make_native(dynamic, monkeypatch)
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    dynamic.backend.plan_step = lambda *args: plan
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked'
    assert 'I can read' in result.declared.blocker
    assert 'rephrase' in result.declared.blocker
    assert 'private-provider-error-details' not in result.declared.blocker
    assert len(dynamic.shown) == 1 and dynamic.shown[0].last


def test_native_human_stuck_does_not_claim_accessibility_was_lost(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.it._on_guidance = lambda step: dynamic.shown.append(step) or (False, "I cannot find this")
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked'
    assert "You're still stuck" in result.declared.blocker
    assert 'accessibility' not in result.declared.blocker.lower()
    assert len(dynamic.calls) == 1


@pytest.mark.parametrize('role,enabled,kind,target', [
    ('AXStaticText', None, 'click', 0),
    ('AXButton', False, 'click', 0),
    ('AXButton', True, 'type', 0),
    ('AXButton', None, 'click', None),
])
def test_unusable_action_is_replanned_once_without_showing_an_arrow(dynamic, monkeypatch, role, enabled, kind, target):
    _make_native(dynamic, monkeypatch)
    _, items = dynamic.backend.page_catalogue(None)
    items[0].role, items[0].enabled = role, enabled
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    dynamic.backend.plan_step = lambda *args: dynamic.calls.append(args) or {
        'done': False, 'instruction': 'Use Details', 'kind': kind, 'target': target}
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked'
    assert len(dynamic.calls) == 2
    assert len(dynamic.shown) == 1 and dynamic.shown[0].last
    assert dynamic.shown[0].pointer is None
    assert 'Instruction NOT shown' in '\n'.join(result.declared.steps_taken)


def test_unknown_enabled_and_selected_button_remain_usable_context(dynamic):
    _, items = dynamic.backend.page_catalogue(None)
    items[0].enabled, items[0].selected = None, True
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert dynamic.shown[0].box_exact
    assert 'enabled=None' in dynamic.calls[0][3][0] and 'selected=True' in dynamic.calls[0][3][0]


def test_no_change_prevents_reworded_click_on_same_target_and_is_traced(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    monkeypatch.setattr(dynamic.it, '_wait_page_change', lambda *args: 'unchanged')
    plans = iter(['Click Details', 'Open Details', 'Press Details'])
    histories = []

    def plan(*args):
        histories.append(list(args[4]))
        return {'done': False, 'instruction': next(plans), 'kind': 'click', 'target': 0}

    dynamic.backend.plan_step = plan
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked'
    assert [s.instruction for s in dynamic.shown[:-1]] == ['Click Details']
    assert 'No visible accessibility change' in '\n'.join(histories[1])
    assert 'was already tried' in '\n'.join(histories[2])
    assert any('No visible accessibility change' in step.summary for step in dynamic.it.steps)


def test_no_change_can_recover_through_different_visible_target(dynamic, monkeypatch):
    _, items = dynamic.backend.page_catalogue(None)
    alternative = SimpleNamespace(role='AXPopUpButton', name='More', center=(200, 100), box=(180, 80, 40, 40))
    dynamic.backend.page_catalogue = lambda _: (dynamic.info, [items[0], alternative])
    plans = iter([
        {'done': False, 'instruction': 'Open Details', 'kind': 'click', 'target': 0},
        {'done': False, 'instruction': 'Open More', 'kind': 'click', 'target': 1},
        {'done': True, 'summary': 'The menu is visible.'},
    ])
    changes = iter(['unchanged', 'changed'])
    dynamic.backend.plan_step = lambda *args: next(plans)
    monkeypatch.setattr(dynamic.it, '_wait_page_change', lambda *args: next(changes))
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert [s.instruction for s in dynamic.shown[:2]] == ['Open Details', 'Open More']
    assert any('goal completion is not verified' in step.summary for step in dynamic.it.steps)


def test_rewording_and_layout_jitter_cannot_repeat_a_clicked_target(dynamic):
    """Odoo CRM stayed open while geometry/order changes unlocked the same click six times."""
    from hcs_agent.a11y import Candidate
    controls = [Candidate('AXMenuItem', 'CRM', (60, 170, 45, 26)),
                Candidate('AXSearchField', 'Rechercher…', (400, 210, 300, 30))]
    dynamic.backend.page_catalogue = lambda _: (dynamic.info, list(controls))
    plans = iter([
        {'instruction': 'Open CRM', 'kind': 'click', 'target': 0},
        {'instruction': 'Click CRM again', 'kind': 'click', 'target': 1},
        {'instruction': 'Search for the requested opportunity', 'kind': 'type', 'target': 0, 'text': 'Example'},
        {'done': True, 'summary': 'The result is visible.'},
    ])
    dynamic.backend.plan_step = lambda *args: next(plans)

    def interact(step):
        dynamic.shown.append(step)
        if step.where == 'CRM':
            controls[0].frame = (61, 171, 45, 26)
            controls.reverse()
        return True, 'Observed interaction; result not verified.'

    dynamic.it._on_guidance = interact
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert [s.where for s in dynamic.shown if not s.last] == ['CRM', 'Rechercher…']
    assert any('already clicked in this same visible page state' in s.summary for s in dynamic.it.steps)


def test_toggling_between_two_catalogues_does_not_reset_tried_target(dynamic):
    from hcs_agent.a11y import Candidate
    controls = [Candidate('AXPopUpButton', 'CRM', (60, 170, 45, 26))]
    option = Candidate('AXMenuItem', 'Pipeline', (60, 200, 120, 30))
    dynamic.backend.page_catalogue = lambda _: (dynamic.info, list(controls))
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    dynamic.backend.plan_step = lambda *a: {'instruction': f'Open CRM ({len(dynamic.shown)})',
                                          'kind': 'click', 'target': 0}

    def interact(step):
        dynamic.shown.append(step)
        if len(controls) == 1:
            controls.append(option)
        else:
            controls.pop()
        return True, 'Observed interaction; result not verified.'

    dynamic.it._on_guidance = interact
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked'
    assert len([s for s in dynamic.shown if s.kind == 'click']) == 2
    assert dynamic.shown[-1].last


def test_unchanged_input_focus_does_not_block_typing_in_the_same_field(dynamic, monkeypatch):
    _, items = dynamic.backend.page_catalogue(None)
    items[0].role = 'AXTextField'
    plans = iter([
        {'done': False, 'instruction': 'Click Search', 'kind': 'click', 'target': 0},
        {'done': False, 'instruction': 'Type an example', 'kind': 'type', 'target': 0, 'text': 'example'},
        {'done': True, 'summary': 'The result is visible.'},
    ])
    histories = []

    def plan(*args):
        histories.append(list(args[4]))
        return next(plans)

    dynamic.backend.plan_step = plan
    monkeypatch.setattr(dynamic.it, '_wait_page_change', lambda *args: 'unchanged')
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert [s.kind for s in dynamic.shown[:2]] == ['click', 'type']
    assert 'not proof that an edit failed' in '\n'.join(histories[1])
    assert not any('action rejected' in step.summary for step in dynamic.it.steps)


@pytest.mark.parametrize('change', ['selection', 'position', 'enabled', 'title', 'response_text'])
def test_accessibility_change_detects_more_than_label_changes(dynamic, change):
    from hcs_agent.runner import _page_state_signature
    info, items = dynamic.backend.page_catalogue(None)
    before = _page_state_signature(info, items)
    if change == 'selection':
        items[0].selected = True
    elif change == 'position':
        items[0].box = (80, 140, 40, 40)
    elif change == 'enabled':
        items[0].enabled = False
    elif change == 'response_text':
        info.readable_text = ('AGENT ANSWER', 'The requested answer is now displayed.')
    else:
        info.title = 'A new view with the same labels'
    expected = 'unchanged' if change == 'position' else 'changed'
    assert Intervention._wait_page_change(dynamic.it, dynamic.backend.page_catalogue, dynamic.bound, before) == expected


def test_read_only_response_is_sent_to_planner_without_becoming_a_target(dynamic):
    dynamic.info.readable_text = ('AGENT ANSWER', 'A response exists; the stop reason is not shown.')
    dynamic.it._dynamic_guide(dynamic.bound)
    assert 'A response exists; the stop reason is not shown.' in dynamic.calls[0][2]
    assert 'untrusted page data' in dynamic.calls[0][2]
    assert all('A response exists' not in candidate for candidate in dynamic.calls[0][3])


@pytest.mark.parametrize('summary', [None, '', '  ', 42, {'wrong': 'type'}])
def test_terminal_info_instruction_survives_missing_summary(dynamic, summary):
    answer = 'Yes. The session produced an answer in the AGENT ANSWER panel.'
    dynamic.backend.plan_step = lambda *args: {'done': True, 'kind': 'info',
                                               'instruction': answer, 'summary': summary}
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done'
    assert result.declared.summary == answer == dynamic.shown[0].instruction
    assert len(dynamic.shown) == 1 and dynamic.shown[0].last


def test_missing_terminal_answer_gets_one_repair_without_generic_success(dynamic):
    plans = iter([{'done': True, 'kind': 'info', 'instruction': ''},
                  {'done': True, 'summary': 'Yes. The final answer is displayed on the right.'}])
    calls = []
    dynamic.backend.plan_step = lambda *args: calls.append(args) or next(plans)
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done' and len(calls) == 2
    assert len(dynamic.shown) == 1
    assert 'final answer is displayed' in dynamic.shown[0].instruction
    assert 'omitted the factual answer' in calls[1][4][-1]


@pytest.mark.parametrize('plan', [
    {'done': True, 'kind': 'info', 'instruction': ''},
    {'done': True, 'kind': 'click', 'instruction': 'Click Answer'},
    {'done': True, 'summary': 123, 'instruction': None},
])
def test_repeated_empty_terminal_answer_blocks_instead_of_success(dynamic, plan):
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    calls = []
    dynamic.backend.plan_step = lambda *args: calls.append(args) or plan
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked' and len(calls) == 2
    assert len(dynamic.shown) == 1 and dynamic.shown[0].last
    assert 'reliable answer' in dynamic.shown[0].instruction
    assert 'Goal reached' not in result.declared.summary


@pytest.mark.parametrize('unavailable', ['missing', 'background', 'empty'])
def test_lost_page_is_unknown_progress_not_a_change(dynamic, unavailable):
    from hcs_agent.runner import _page_state_signature
    info, items = dynamic.backend.page_catalogue(None)
    before = _page_state_signature(info, items)
    if unavailable == 'background':
        info.is_front = False
    catalogue = lambda _: None if unavailable == 'missing' else (info, [] if unavailable == 'empty' else items)
    assert Intervention._wait_page_change(dynamic.it, catalogue, dynamic.bound, before) == 'unavailable'


def test_unchanged_wait_is_bounded_and_stop_is_preserved(dynamic, monkeypatch):
    from hcs_agent.runner import _page_state_signature
    before = _page_state_signature(*dynamic.backend.page_catalogue(None))
    clock = iter([0.0, 0.1, 1.7])
    monkeypatch.setattr('hcs_agent.runner.time.monotonic', lambda: next(clock))
    monkeypatch.setattr('hcs_agent.runner.time.sleep', lambda _: None)
    assert Intervention._wait_page_change(dynamic.it, dynamic.backend.page_catalogue, dynamic.bound, before) == 'unchanged'
    monkeypatch.setattr('hcs_agent.runner.time.monotonic', lambda: 0.0)
    dynamic.it._stop.set()
    assert Intervention._wait_page_change(dynamic.it, dynamic.backend.page_catalogue, dynamic.bound, before) == 'stopped'


def test_invalidated_target_can_be_reobserved_once_without_claiming_an_action(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    note = 'Observation only: target invalidated; reobserve requested. No target interaction confirmed.'
    dynamic.it._on_guidance = lambda step: dynamic.shown.append(step) or (False, note)
    histories = []

    def plan(*args):
        histories.append(list(args[4]))
        return {'done': False, 'instruction': 'Open Details', 'kind': 'click', 'target': 0}

    dynamic.backend.plan_step = plan
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert len(histories) == 2  # Repeated invalidations cannot create an unbounded paid planning loop.
    assert histories[1] == [note]
    assert result.declared.outcome == 'blocked'
    assert not any('Instruction shown:' in entry for entry in histories[1])


def test_successful_interaction_renews_bounded_reobservation_budget(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    note = 'Observation only: target invalidated; reobserve requested. No target interaction confirmed.'
    replies = iter([(False, note), (True, 'Observed interaction: target click.'), (False, note)])
    count = [0]
    def plan(*args):
        count[0] += 1
        return ({'done': True, 'summary': 'Answer is displayed.'} if count[0] == 4 else
                {'done': False, 'instruction': 'Open Details', 'kind': 'click', 'target': 0})
    def guidance(step):
        dynamic.shown.append(step)
        if step.last:
            return True, ''
        reply = next(replies)
        if reply[0]:
            dynamic.info.title = 'New view after the click'
        return reply
    dynamic.backend.plan_step = plan
    dynamic.it._on_guidance = guidance
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'done' and count[0] == 4
    assert len([x for x in result.declared.steps_taken if x.startswith('Instruction shown:')]) == 1


def test_native_front_window_timeout_has_specific_observation(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    dynamic.info.is_front = False
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    monkeypatch.setattr('hcs_agent.runner.time.sleep', lambda _: None)
    result = dynamic.it._dynamic_guide(dynamic.bound, max_steps=42)
    assert result.declared.outcome == 'blocked'
    assert 'focused Devin window' in result.declared.blocker
    assert dynamic.calls == []


def test_native_catalogue_lost_after_planning_is_reported_without_arrow(dynamic, monkeypatch):
    _make_native(dynamic, monkeypatch)
    info, items = dynamic.backend.page_catalogue(None)
    views = iter([(info, items), None])
    dynamic.backend.page_catalogue = lambda _: next(views)
    dynamic.it._on_guidance_nowait = dynamic.shown.append
    result = dynamic.it._dynamic_guide(dynamic.bound)
    assert result.declared.outcome == 'blocked'
    assert 'could no longer be read' in result.declared.blocker
    assert len(dynamic.calls) == 1 and len(dynamic.shown) == 1
    assert dynamic.shown[0].pointer is None
