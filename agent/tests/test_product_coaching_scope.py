"""Keep speech ambiguity inside the selected product without rewriting evidence."""
import argparse
import json
from types import SimpleNamespace

import httpx

from hcs_agent import cli, voice
from hcs_agent.a11y import PageInfo
from hcs_agent.app_context import make_request
from hcs_agent.contract import Mode
from hcs_agent.grounding import Grounder
from hcs_agent.procedures import PRODUCT_COACHING_SCOPE, ProcedureRegistry


def test_ambiguous_transcript_does_not_change_product_or_get_silently_rewritten():
    transcript = "Hello, give me a quick welcome to Orkney."
    page = PageInfo(app='Google Chrome', title='Sessions', url='https://platform.hcompany.ai/agents/sessions')
    request, status = make_request(transcript, page, SimpleNamespace(ask=lambda *_a, **_k: None))
    assert request.goal == transcript and request.software == 'h-company'
    assert status['label'] == 'H Company'
    for mode in (Mode.act, Mode.guide):
        request.mode = mode
        bound = ProcedureRegistry().for_request(request).bound(request)
        assert PRODUCT_COACHING_SCOPE in bound.agent_instructions
        assert PRODUCT_COACHING_SCOPE in bound.guide_instructions
        assert 'Selected software: H Company.' in bound.task_message()
        assert 'User goal: ' + transcript in bound.task_message()
        assert request.goal == transcript


def test_text_planner_carries_scope_and_retains_clarification_as_non_action():
    calls = []
    question = "Did you mean a quick tour of H Platform?"
    def provider(request):
        body = json.loads(request.content)
        calls.append(body)
        assert PRODUCT_COACHING_SCOPE in body['messages'][0]['content']
        return httpx.Response(200, json={'choices': [{'message': {'tool_calls': [{
            'function': {'name': 'next_step', 'arguments': json.dumps({
                'observation': 'H Platform Sessions is visible.', 'done': False, 'blocked': True,
                'kind': 'info', 'target': 0, 'instruction': question, 'summary': '',
            })}}]}}]})
    grounder = object.__new__(Grounder)
    grounder.model = 'offline'
    grounder._http = httpx.Client(transport=httpx.MockTransport(provider))
    try:
        result = grounder.plan_step('Give me a welcome to an unexpected place.', 'Selected software: H Company.',
                                    'H Platform Sessions', ["Button 'Skills'"], [])
    finally:
        grounder._http.close()
    assert result['instruction'] == question
    assert result['target'] is None and result['done'] is False and result['blocked'] is True
    assert len(calls) == 1  # no added classification call or screenshot upload
    assert isinstance(calls[0]['messages'][0]['content'], str)


def test_automatic_talk_wires_product_names_into_the_real_ptt_constructor(tmp_path, monkeypatch):
    captured = []
    class PTT:
        key_name = 'alt_r'
        def __init__(self, **kwargs):
            captured.append(kwargs['vocabulary'])
            self.transcripts = SimpleNamespace(empty=lambda: True)
        def start(self): pass
        def stop(self): pass
        def wait_transcript(self, **kwargs): raise KeyboardInterrupt
    monkeypatch.setattr(voice, 'PushToTalk', PTT)
    monkeypatch.setattr(voice, 'IntentRouter', lambda *_a: (_ for _ in ()).throw(AssertionError('No generic router in auto mode')))
    monkeypatch.setattr(cli, 'make_backend', lambda *_a: SimpleNamespace())
    monkeypatch.setattr(cli, '_start_control', lambda *_a: None)
    monkeypatch.setattr(cli, '_APP_CONTEXT', {})
    monkeypatch.setattr(cli, '_VOICE', {})
    monkeypatch.setitem(cli._SPEECH, 'speaker', None)
    monkeypatch.setitem(cli._MAGNET, 'widget', None)
    monkeypatch.setitem(cli._MAGNET, 'current', None)
    monkeypatch.setenv('HCS_AUTO_CONTEXT', '0')
    monkeypatch.setenv('HCS_AX_NATIVE_BUNDLE_ID', 'test-only')
    args = argparse.Namespace(software='auto', no_overlay=True, mock=True, runs_dir=str(tmp_path),
                              key='alt_r', confirm=False, once=True)
    assert cli.cmd_talk(args) == 0
    assert captured == [list(voice.AUTO_PRODUCT_VOCABULARY)]
    assert 'H Platform' in captured[0] and 'Acme Demo' not in captured[0]
