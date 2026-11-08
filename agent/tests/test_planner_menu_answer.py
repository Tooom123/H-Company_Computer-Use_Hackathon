"""Planner request/response contract for answering from an already open menu. No model or AX calls."""

import json

import httpx

from hcs_agent.grounding import Grounder


def test_text_planner_can_answer_visible_choices_without_requesting_another_action():
    requests = []

    def provider(request):
        body = json.loads(request.content)
        requests.append(body)
        prompt = body['messages'][0]['content']
        assert 'Menu options visible now' in prompt
        assert "MenuItem 'Regular'" in prompt and "MenuItem 'Bold'" in prompt
        assert 'do not ask to reopen their menu' in prompt
        assert 'Visibility alone does not prove a choice is selected' in prompt
        assert 'unavailable evidence' in str(body['tools'])
        schema = body['tools'][0]['function']['parameters']
        assert 'summary' in schema['required']
        return httpx.Response(200, json={'choices': [{'message': {'tool_calls': [{
            'function': {'name': 'next_step', 'arguments': json.dumps({
                'done': True, 'kind': 'info', 'target': 0,
                'instruction': 'Regular and Bold are visible.',
                'summary': 'The available text styles are Regular and Bold.',
            })},
        }]}}]})

    grounder = object.__new__(Grounder)
    grounder.model = 'offline-test'
    grounder._http = httpx.Client(transport=httpx.MockTransport(provider))
    try:
        result = grounder.plan_step('Show the text styles without changing them.', 'Read-only coaching.',
            'Document editor\nMenu options visible now: 2. Regular; 3. Bold',
            ["PopUpButton 'Text style'", "MenuItem 'Regular'", "MenuItem 'Bold'"],
            ['Click observed; result not verified.'])
    finally:
        grounder._http.close()
    assert result['done'] is True and result['kind'] == 'info' and result['target'] is None
    assert len(requests) == 1
    assert isinstance(requests[0]['messages'][0]['content'], str)  # Text only; no screenshot upload.
