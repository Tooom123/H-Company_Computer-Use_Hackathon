"""Offline protocol tests for the isolated H Platform coach.

These check what can reach the executor, not whether Holo understands a tour.
The latter still needs a recorded live human evaluation.
"""
import copy
import json

import httpx
import pytest
from pydantic import ValidationError

from hcs_agent.coach_v2 import (
    CoachClient, CoachDecision, CoachProtocolError, allowed_docs_url, allowed_page,
    sensitive_key_creation,
)


@pytest.fixture
def observation():
    return {
        "url": "https://platform.hcompany.ai/agents/sessions/example",
        "title": "H Platform — Sessions",
        "controls": [
            {"id": 1, "role": "AXButton", "label": "Sessions", "box": [10, 20, 90, 30]},
            {"id": 4, "role": "AXTextField", "label": "Search sessions", "box": [110, 20, 180, 30]},
            {"id": 7, "role": "AXStaticText", "label": "Agent answer", "box": [110, 80, 180, 30]},
        ],
        "text": ["Interrupted", "Agent answer", "The product costs ten euros."],
    }


def step(**changes):
    decision = {"speech": "The session contains an answer. You can read it in the Agent answer panel.",
                "action": "explain", "target": 7, "text": None, "direction": None,
                "key": None, "url": None}
    decision.update(changes)
    return decision


def envelope(decision, name="coach_step"):
    return {"choices": [{"message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {
                "name": name, "arguments": json.dumps(decision)}}]}}],
            "usage": {"prompt_tokens": 245, "completion_tokens": 51}}


def tool(body, action):
    return next(item["function"] for item in body["tools"] if item["function"]["name"] == "coach_" + action)


@pytest.fixture
def client_factory():
    clients = []

    def create(decision=None, *, payload=None, status=200):
        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(status, json=payload if payload is not None else envelope(decision or step()))

        client = CoachClient("private-test-key", transport=httpx.MockTransport(handler))
        clients.append(client)
        return client, requests

    yield create
    for client in clients:
        client.close()


def test_one_bounded_call_uses_current_evidence_and_preserves_question(observation, client_factory):
    client, requests = client_factory()
    before = copy.deepcopy(observation)
    decision = client.decide("Give me a quick welcome tour of Orkney", observation, "guide")
    assert decision.action == "explain" and decision.target == 7
    assert observation == before
    assert len(requests) == 1
    body = requests[0]
    assert body["model"] == "holo4-35b-a3b"
    assert body["max_tokens"] == 700  # A requested three-point tour has room for three short annotations.
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["temperature"] == 0
    tools = body["tools"]
    assert all(item["function"]["strict"] is True for item in tools)
    assert all(item["function"]["parameters"]["additionalProperties"] is False for item in tools)
    assert all(set(item["function"]["parameters"]["required"]) ==
               set(item["function"]["parameters"]["properties"]) for item in tools)
    assert "coach_step" not in {item["function"]["name"] for item in tools}
    sent = json.loads(body["messages"][1]["content"])
    assert sent["mode"] == "guide"
    assert sent["question"] == "Give me a quick welcome tour of Orkney"
    assert sent["current_observation"]["text"] == observation["text"]
    assert client.last_raw == step()
    assert client.last_usage["completion_tokens"] == 51
    assert client.last_latency_s >= 0


def test_semantic_ax_payload_preserves_every_target_without_sending_geometry(observation, client_factory):
    observation["controls"][0]["enabled"] = True
    observation["controls"][1]["enabled"] = False
    before = copy.deepcopy(observation)
    client, requests = client_factory()
    client.decide("What answer is visible?", observation, "guide")
    body = requests[0]
    sent = json.loads(body["messages"][1]["content"])
    controls = sent["current_observation"]["controls"]
    assert [(c["id"], c["role"], c["label"]) for c in controls] == [
        (c["id"], c["role"], c["label"]) for c in observation["controls"]]
    assert controls[0]["enabled"] is True
    assert controls[1]["enabled"] is False
    assert "enabled" not in controls[2]
    assert all("box" not in control for control in controls)
    assert observation == before
    # Compaction neither removes descriptions/constraints nor changes output validation.
    schema = tool(body, "type")["parameters"]
    assert schema["additionalProperties"] is False
    assert "description" in schema["properties"]["text"]
    assert "title" not in schema and "default" not in schema["properties"]["text"]
    assert sent["current_observation"]["text"] == observation["text"]


def test_mode_rule_reinforces_english_and_does_not_promise_guide_actions(observation, client_factory):
    client, requests = client_factory()
    client.decide("Crée une clé pour moi", observation, "guide")
    system = requests[0]["messages"][0]["content"]
    assert "All speech and tour-point speech must be English" in system
    assert "never promise that you will click or type" in system
    request = json.loads(requests[0]["messages"][1]["content"])
    assert request["response_language"] == "English"
    assert "You guide:" in request["response_instructions"]


@pytest.mark.parametrize("url", [
    "http://platform.hcompany.ai/agents", "https://platform.hcompany.ai.evil.example/",
    "https://platform.hcompany.ai@evil.example/", "https://user@platform.hcompany.ai/",
    "https://platform.hcompany.ai:444/", "https://platform.hcompany.ai/vaults",
    "https://platform.hcompany.ai/credentials", "https://platform.hcompany.ai/auth/login",
    "https://platform.hcompany.ai/\n/agents", None, ["https://platform.hcompany.ai/"],
])
def test_out_of_scope_observation_never_calls_provider(url, observation, client_factory):
    client, requests = client_factory()
    observation["url"] = url
    with pytest.raises(CoachProtocolError):
        client.decide("Show me this page", observation, "guide")
    assert requests == []


def test_official_docs_about_credentials_are_readable():
    assert allowed_page("https://hub.hcompany.ai/agents-api/vaults")
    assert allowed_docs_url("https://hub.hcompany.ai/agents-api/overview#quickstart")


def test_open_docs_cannot_create_a_targetless_guide_wait(observation, client_factory):
    raw = step(action="open_docs", target=None, url="https://hub.hcompany.ai/agents-api/browser/profiles")
    client, requests = client_factory(raw)
    with pytest.raises(CoachProtocolError, match="requires act mode"):
        client.decide("Open the profiles documentation", observation, "guide")
    assert client.decide("Open the profiles documentation", observation, "act").action == "open_docs"
    assert "coach_open_docs" not in {item["function"]["name"] for item in requests[0]["tools"]}
    assert tool(requests[1], "open_docs")


@pytest.mark.parametrize("url", [
    "https://platform.hcompany.ai/agents", "https://hub.hcompany.ai.evil.example/",
    "javascript:alert(1)", "https://hub.hcompany.ai:8443/", "https://me@hub.hcompany.ai/",
])
def test_open_docs_rejects_non_official_destinations(url):
    with pytest.raises(ValidationError):
        CoachDecision(**step(action="open_docs", target=None, url=url))


@pytest.mark.parametrize("target", [99, 0, True, "1"])
def test_model_must_use_an_exact_observed_integer_target(target, observation, client_factory):
    raw = step(action="click", target=target, speech="Open Sessions to find your recent runs.")
    client, requests = client_factory(raw)
    with pytest.raises(CoachProtocolError):
        client.decide("Show my sessions", observation, "act")
    assert len(requests) == 1
    assert client.last_raw == raw  # Rejected output remains traceable.


@pytest.mark.parametrize("label", ["Delete session", "Vaults", "Run", "Start agent", "Pay", "Upgrade"])
def test_sensitive_controls_are_not_executable(label, observation, client_factory):
    observation["controls"][0]["label"] = label
    client, _ = client_factory(step(action="click", target=1, speech="Open this area."))
    with pytest.raises(CoachProtocolError):
        client.decide("Open this", observation, "act")


def test_disabled_control_is_not_executable(observation, client_factory):
    observation["controls"][0]["enabled"] = False
    client, _ = client_factory(step(action="click", target=1))
    with pytest.raises(CoachProtocolError):
        client.decide("Open sessions", observation, "act")


def test_typing_requires_a_text_input_and_literal_text(observation, client_factory):
    client, _ = client_factory(step(action="type", target=4, text="companion-demo"))
    assert client.decide("Find my demo", observation, "act").text == "companion-demo"
    client, _ = client_factory(step(action="type", target=1, text="companion-demo"))
    with pytest.raises(CoachProtocolError):
        client.decide("Find my demo", observation, "act")
    assert CoachDecision(**step(action="type", target=4, text="companion-demo\n")).text == "companion-demo\n"
    with pytest.raises(ValidationError):
        CoachDecision(**step(action="type", target=4, text="companion-demo\x1b"))


@pytest.mark.parametrize("speech", [
    "Result: Done", "**Summary:** Here is what happened.", "# Sessions\nAn overview.",
    "| Name | Status |", "```python\nprint('done')\n```", '{"result": "done"}',
    "word " * 33, "A" * 221, "1. Sessions\n2. Agents",
])
def test_report_code_or_novel_cannot_reach_voice_or_executor(speech, observation, client_factory):
    client, _ = client_factory(step(speech=speech, action="click", target=1))
    with pytest.raises(CoachProtocolError):
        client.decide("Show me around", observation, "act")


def test_done_can_end_silently_without_a_recap():
    assert CoachDecision(**step(action="done", target=None, speech="")).speech == ""
    with pytest.raises(ValidationError):
        CoachDecision(**step(speech=""))


def test_short_three_sentence_welcome_is_not_a_novel(observation, client_factory):
    raw = step(speech="Welcome to H Platform! This page shows your agent sessions, each run of an agent. You can explore Agents, Skills, and Sessions here.")
    client, _ = client_factory(raw)
    answer = client.decide("Give me a tour of this page", observation, "guide")
    assert answer.speech == raw["speech"]
    assert len(answer.speech.split()) <= 32 and len(answer.speech) <= 220


@pytest.mark.parametrize("sentinel", ["", "None", "null", " NONE "])
@pytest.mark.parametrize("field", ["target", "text", "direction", "key", "url"])
def test_unused_null_spellings_do_not_discard_a_useful_explanation(field, sentinel, observation, client_factory):
    raw = step(**{field: sentinel})
    before = copy.deepcopy(raw)
    client, _ = client_factory(raw)
    answer = client.decide("What are these for?", observation, "guide")
    assert getattr(answer, field) is None
    assert answer.speech == raw["speech"]
    assert client.last_raw == before  # Keep the provider payload exactly as received for diagnosis.
    assert raw == before


@pytest.mark.parametrize("literal", ["None", "null", " NONE "])
def test_typing_a_literal_null_word_remains_literal(literal, observation, client_factory):
    client, _ = client_factory(step(action="type", target=4, text=literal))
    assert client.decide("Find this exact text", observation, "act").text == literal


@pytest.mark.parametrize("changes", [
    {"action": "click", "target": "None"},
    {"action": "type", "target": 4, "text": ""},
    {"action": "scroll", "target": None, "direction": "None"},
    {"action": "key", "target": None, "key": ""},
    {"action": "open_docs", "target": None, "url": "null"},
    {"action": "explain", "text": "delete all"},
    {"action": "explain", "url": "https://hub.hcompany.ai/agents-api/overview"},
])
def test_null_normalization_never_repairs_missing_required_or_real_extra_arguments(changes):
    with pytest.raises(ValidationError):
        CoachDecision(**step(**changes))


def test_protocol_diagnostics_distinguish_reading_provider_and_output(observation, client_factory):
    client, _ = client_factory(step(text="unexpected-private-text"))
    with pytest.raises(CoachProtocolError) as captured:
        client.decide("Explain Skills", observation, "guide")
    error = captured.value
    assert error.kind == "response" and error.reason == "invalid_step"
    assert error.validation_errors
    assert "unexpected-private-text" not in json.dumps(error.validation_errors)

    client, _ = client_factory(status=429)
    with pytest.raises(CoachProtocolError) as captured:
        client.decide("Explain Skills", observation, "guide")
    assert captured.value.kind == "provider" and captured.value.reason == "http_429"

    client, requests = client_factory()
    with pytest.raises(CoachProtocolError) as captured:
        client.decide("Explain Skills", {**observation, "url": "https://example.org"}, "guide")
    assert captured.value.kind == "observation"
    assert not requests


@pytest.mark.parametrize("changes", [
    {"action": "click", "target": None}, {"action": "scroll", "target": None},
    {"action": "explain", "direction": "down"}, {"action": "key", "target": None, "key": "cmd+r"},
    {"action": "done", "target": None, "text": "unused"}, {"action": "explain", "coordinates": [10, 20]},
])
def test_action_shape_is_not_ambiguous(changes):
    with pytest.raises(ValidationError):
        CoachDecision(**step(**changes))


@pytest.mark.parametrize("payload", [[], {"choices": []}, {"choices": [{"message": []}]},
    {"choices": [{"message": {"content": "Hello", "tool_calls": []}}]},
    {"choices": [{"message": {"tool_calls": [None]}}]},
])
def test_bad_provider_envelopes_fail_closed(payload, observation, client_factory):
    client, _ = client_factory(payload=payload)
    with pytest.raises(CoachProtocolError):
        client.decide("Show me around", observation, "guide")


def test_multiple_tool_calls_are_not_partially_executed(observation, client_factory):
    payload = envelope(step())
    payload["choices"][0]["message"]["tool_calls"] *= 2
    client, _ = client_factory(payload=payload)
    with pytest.raises(CoachProtocolError):
        client.decide("Show me around", observation, "act")


def test_provider_failure_never_leaks_body(observation, client_factory):
    client, _ = client_factory(payload={"error": "secret-provider-content"}, status=403)
    with pytest.raises(CoachProtocolError, match="^Holo returned HTTP 403\\.$"):
        client.decide("Show me around", observation, "guide")


def test_history_is_bounded_and_has_no_old_images_or_provider_reasoning(observation, client_factory):
    history = [{"speech": "x" * 1000, "question": str(i), "screenshot": "private-image", "reasoning": "private-reason"}
               for i in range(10)]
    client, requests = client_factory()
    client.decide("Show me around", observation, "guide", history)
    sent = json.loads(requests[0]["messages"][1]["content"])
    assert len(sent["recent_history"]) == 4
    assert sent["recent_history"][0]["question"] == "6"
    assert len(sent["recent_history"][0]["speech"]) == 600
    assert "private-image" not in requests[0]["messages"][1]["content"]
    assert "private-reason" not in requests[0]["messages"][1]["content"]


@pytest.mark.parametrize("bad_box", [[-1, 20, 30, 40], [0, 20, 0, 40], [0, 20, float("nan"), 40], [1, 2, 3]])
def test_unusable_geometry_is_rejected_before_request(bad_box, observation, client_factory):
    observation["controls"][0]["box"] = bad_box
    client, requests = client_factory()
    with pytest.raises(CoachProtocolError):
        client.decide("Show me around", observation, "guide")
    assert requests == []


@pytest.mark.parametrize('url', [
    'https://platform.hcompany.ai/api-keys',
    'https://platform.hcompany.ai/%61pi-keys',
    'https://platform.hcompany.ai/organisation/billing',
    'https://platform.hcompany.ai/plans',
])
def test_account_configuration_pages_are_in_scope_for_safe_observer(url):
    assert allowed_page(url)


@pytest.mark.parametrize('label', ['API keys', 'Billing', 'Plans', 'Current plan'])
def test_account_navigation_controls_are_allowed(label, observation, client_factory):
    observation['controls'][0]['label'] = label
    client, _ = client_factory(step(action='click', target=1, speech='Open this section.'))
    assert client.decide('Show me the account configuration', observation, 'act').action == 'click'


def tour_step():
    return step(action='tour', target=None, speech='H Platform helps you build agents and review their work.',
                points=[{'target': 1, 'speech': 'Sessions show the progress and answers from individual runs.'}])


def test_requested_tour_has_short_observed_points_and_no_clicks(observation, client_factory):
    client, requests = client_factory(tour_step())
    answer = client.decide('Hey Companion, give me a quick tour.', observation, 'guide')
    assert answer.action == 'tour' and answer.target is None
    assert answer.points[0].target == 1
    assert answer.points[0].speech.startswith('Sessions')
    assert requests[0]['max_tokens'] == 700


def test_tour_is_not_invented_for_unrelated_question(observation, client_factory):
    client, _ = client_factory(tour_step())
    with pytest.raises(CoachProtocolError) as caught:
        client.decide('What is a Skill?', observation, 'guide')
    assert caught.value.reason == 'unrequested_tour'


@pytest.mark.parametrize('points', [None, [], [{'speech': 'Hello.', 'target': 1}] * 4,
    [{'speech': 'Hello.', 'target': 1}, {'speech': 'Again.', 'target': 1}],
    [{'speech': 'word ' * 33, 'target': 1}],
])
def test_tour_rejects_missing_repeated_or_overlong_points(points):
    with pytest.raises(ValidationError):
        CoachDecision(**{**tour_step(), 'points': points})


@pytest.mark.parametrize('target', [99, 7])
def test_tour_targets_must_exist_and_be_navigation_controls(target, observation, client_factory):
    client, _ = client_factory({**tour_step(), 'points': [{'speech': 'Here is this section.', 'target': target}]})
    with pytest.raises(CoachProtocolError):
        client.decide('Show me around', observation, 'guide')


def test_only_tour_may_carry_points():
    with pytest.raises(ValidationError):
        CoachDecision(**step(points=[{'speech': 'Here are your sessions.', 'target': 1}]))


def test_unused_empty_points_are_benign_and_raw_payload_is_preserved(observation, client_factory):
    raw = step(points=[])
    client, _ = client_factory(raw)
    assert client.decide('Explain this page.', observation, 'guide').points is None
    assert client.last_raw['points'] == []


def test_markdown_skill_body_is_literal_multiline_payload_not_narration(observation, client_factory):
    observation['controls'][1]['role'] = 'AXTextArea'
    content = '# Guided onboarding\n\nExplain one step at a time.\nWait for the user to act.\nNever perform the task yourself.'
    client, requests = client_factory(step(action='type', target=4, text=content, speech="I'll enter the coaching instructions."))
    decision = client.decide('Create a skill called guided-onboarding', observation, 'act')
    assert decision.text == content
    assert len(decision.speech.split()) <= 32
    assert requests[0]['max_tokens'] == 1500
    assert CoachDecision(**step(action='type', target=4, text='x' * 4000)).text == 'x' * 4000
    with pytest.raises(ValidationError):
        CoachDecision(**step(action='type', target=4, text='x' * 4001))


@pytest.mark.parametrize('label', ['Create API key', 'Generate key', 'Add a key', 'New API key'])
def test_explicit_key_creation_requires_runtime_confirmation_anywhere(label, observation):
    observation['controls'][0]['label'] = label
    decision = CoachDecision(**step(action='click', target=1))
    assert sensitive_key_creation(decision, observation)


@pytest.mark.parametrize('label', ['Create an API key', 'New API key'])
def test_key_list_opener_does_not_require_creation_confirmation(label, observation):
    observation['url'] = 'https://platform.hcompany.ai/settings/api-keys'
    observation['controls'][0]['label'] = label
    observation['controls'].extend([
        {'id': 8, 'role': 'AXHeading', 'label': 'API Keys'},
        # The list's sortable Name column is not an editable key-name field.
        {'id': 9, 'role': 'AXButton', 'label': 'Name'},
    ])
    decision = CoachDecision(**step(action='click', target=1))
    assert not sensitive_key_creation(decision, observation)
    observation['controls'] = [c for c in observation['controls'] if c['id'] != 8]
    assert sensitive_key_creation(decision, observation)  # no positive list evidence


@pytest.mark.parametrize('role,label', [
    ('AXTextField', 'Name'), ('AXTextField', 'API key name'),
    ('AXComboBox', 'Expiration'), ('AXPopUpButton', 'Expires after'),
    ('AXTextField', 'Expiry'), ('AXTextArea', 'Name'),
    ('AXHeading', 'Create an API key'), ('AXHeading', 'New API key'),
    ('AXDialog', ''), ('AXSheet', ''), ('AXButton', 'Cancel'),
])
def test_key_opener_label_remains_guarded_when_editor_is_visible(role, label, observation):
    observation['url'] = 'https://platform.hcompany.ai/settings/api-keys'
    observation['controls'][0]['label'] = 'Create an API key'
    observation['controls'].extend([
        {'id': 8, 'role': 'AXHeading', 'label': 'API Keys'},
        {'id': 9, 'role': role, 'label': label},
    ])
    assert sensitive_key_creation(CoachDecision(**step(action='click', target=1)), observation)


@pytest.mark.parametrize('label', ['Create', 'Generate', 'Create API key', 'Generate key'])
def test_list_heading_does_not_exempt_final_or_uncertain_creation_controls(label, observation):
    observation['url'] = 'https://platform.hcompany.ai/settings/api-keys'
    observation['controls'][0]['label'] = label
    observation['controls'].append({'id': 8, 'role': 'AXHeading', 'label': 'API keys'})
    assert sensitive_key_creation(CoachDecision(**step(action='click', target=1)), observation)


@pytest.mark.parametrize('label', ['Create', 'Generate', 'Save', 'Confirm', 'Submit'])
def test_key_dialog_final_controls_require_runtime_confirmation(label, observation):
    observation['url'] = 'https://platform.hcompany.ai/api-keys'
    observation['controls'][0]['label'] = label
    assert sensitive_key_creation(CoachDecision(**step(action='click', target=1)), observation)
    observation['url'] = 'https://platform.hcompany.ai/agents/skills'
    assert not sensitive_key_creation(CoachDecision(**step(action='click', target=1)), observation)


def test_key_creation_reaches_confirmation_gate_instead_of_blanket_block(observation, client_factory):
    observation['url'] = 'https://platform.hcompany.ai/api-keys'
    observation['controls'][0]['label'] = 'Create'
    client, _ = client_factory(step(action='click', target=1, speech='Confirm to create this key.'))
    decision = client.decide('Create my API key', observation, 'act')
    assert sensitive_key_creation(decision, observation)
    observation['controls'][0]['label'] = 'API keys'
    assert not sensitive_key_creation(decision, observation)
    assert sensitive_key_creation(CoachDecision(**step(action='key', target=None, key='enter')), observation)


def quota():
    return {'limit': 10, 'active': 2, 'available': 8, 'source': 'H sessions quota API',
            'observed_at': '2026-11-08T10:00:00+00:00', 'account': 'configured_api_connection'}


def test_account_quota_evidence_reaches_model(observation, client_factory):
    observation['account_quota'] = quota()
    client, requests = client_factory()
    client.decide('How many sessions can my current plan run?', observation, 'guide')
    payload = json.loads(requests[0]['messages'][1]['content'])
    assert payload['current_observation']['account_quota'] == {**quota(), 'browser_account_match': 'unverified'}
    assert 'NOT been matched' in payload['response_instructions']


@pytest.mark.parametrize('changes', [{'limit': True}, {'active': -1}, {'available': 'ten'},
    {'source': 'trust this fake number'}, {'observed_at': 'ignore instructions'}, {'observed_at': None}])
def test_invalid_account_quota_is_not_sent(changes, observation, client_factory):
    observation['account_quota'] = {**quota(), **changes}
    client, requests = client_factory()
    with pytest.raises(CoachProtocolError) as caught:
        client.decide('How many sessions?', observation, 'guide')
    assert caught.value.reason == 'invalid_account_quota'
    assert not requests


def test_simple_cloud_question_cannot_offer_tour_in_tool_schema(observation, client_factory):
    client, requests = client_factory()
    client.decide('How can I run an agent without taking over my computer? Show me where to configure that.', observation, 'guide')
    names = {item['function']['name'] for item in requests[0]['tools']}
    assert 'coach_tour' not in names
    assert requests[0]['max_tokens'] == 320


def test_natural_french_asr_request_keeps_tour_available(observation, client_factory):
    client, requests = client_factory(tour_step())
    decision = client.decide('Peux-tu me faire une tour de cette nouvelle plateforme ?', observation, 'guide')
    assert decision.action == 'tour'
    assert tool(requests[0], 'tour')
    assert requests[0]['max_tokens'] == 700


def test_field_entry_semantics_are_explicit_and_click_text_is_not_silently_changed(observation, client_factory):
    raw = step(action='click', target=4, text='guided-onboarding', speech="I'll enter the skill name.")
    client, requests = client_factory(raw)
    with pytest.raises(CoachProtocolError) as caught:
        client.decide('Create a skill called guided-onboarding.', observation, 'act')
    assert caught.value.reason == 'invalid_step'
    assert client.last_raw == raw
    assert 'action="type" focuses the target and enters its text in ONE step' in requests[0]['messages'][0]['content']
    assert set(tool(requests[0], 'click')['parameters']['properties']) == {'speech', 'target'}


@pytest.mark.parametrize('name,arguments,expected', [
    ('coach_click', {'speech': "I'll open Sessions.", 'target': 1}, 'click'),
    ('coach_type', {'speech': "I'll enter the name.", 'target': 4, 'text': 'guided-onboarding'}, 'type'),
    ('coach_scroll', {'speech': "I'll look further down.", 'direction': 'down'}, 'scroll'),
    ('coach_key', {'speech': "I'll close this dialog.", 'key': 'escape'}, 'key'),
    ('coach_open_docs', {'speech': "I'll open the cloud browser documentation.",
                         'url': 'https://hub.hcompany.ai/agents-api/browser/configuration'}, 'open_docs'),
    ('coach_explain', {'speech': 'The answer is visible here.', 'target': 7}, 'explain'),
    ('coach_done', {'speech': ''}, 'done'),
])
def test_action_specific_tools_normalize_to_runtime_decisions_without_changing_raw(
        name, arguments, expected, observation, client_factory):
    client, _ = client_factory(payload=envelope(arguments, name))
    decision = client.decide('Show me the requested setting.', observation, 'act')
    assert decision.action == expected
    assert client.last_raw == arguments
    assert 'action' not in client.last_raw


def test_tool_contract_exposes_only_usable_arguments(observation, client_factory):
    client, requests = client_factory()
    client.decide('Give me a quick tour.', observation, 'act')
    body = requests[0]
    assert set(tool(body, 'open_docs')['parameters']['properties']) == {'speech', 'url'}
    assert set(tool(body, 'type')['parameters']['properties']) == {'speech', 'target', 'text'}
    assert tool(body, 'type')['parameters']['properties']['target']['type'] == 'integer'
    assert tool(body, 'type')['parameters']['properties']['text']['minLength'] == 1
    assert tool(body, 'type')['parameters']['properties']['text']['type'] == 'string'
    assert set(tool(body, 'tour')['parameters']['$defs']['TourPoint']['required']) == {'speech', 'target'}
    assert not any('action' in item['function']['parameters']['properties'] for item in body['tools'])


@pytest.mark.parametrize('name,arguments', [
    ('coach_delete', {'speech': 'Delete this.'}),
    ('coach_click', {'speech': 'Click this.', 'target': 1, 'action': 'type'}),
    ('coach_type', {'speech': 'Enter the text.', 'target': 4}),
    ('coach_type', {'speech': 'Enter the text.', 'target': 4, 'text': ' \n\t'}),
    ('coach_type', {'speech': 'Enter the text.', 'target': 4, 'text': '',
                    'url': 'https://hub.hcompany.ai/agents-api/browser/configuration'}),
    ('coach_click', {'speech': 'Enter the text.', 'target': 4, 'text': 'unexpected'}),
])
def test_tools_never_invent_missing_text_or_change_actions(name, arguments, observation, client_factory):
    client, _ = client_factory(payload=envelope(arguments, name))
    with pytest.raises(CoachProtocolError):
        client.decide('Show me cloud browsers.', observation, 'act')
    assert client.last_raw in (None, arguments)


@pytest.mark.parametrize('name', ['coach_step', 'coach_open_docs'])
def test_docs_redundant_target_is_ignored_without_clicking_or_rewriting_raw(name, observation, client_factory):
    arguments = {'speech': "I'll open the cloud browser documentation.", 'target': 4,
                 'url': 'https://hub.hcompany.ai/agents-api/browser/configuration'}
    if name == 'coach_step':
        arguments['action'] = 'open_docs'
    client, _ = client_factory(payload=envelope(arguments, name))
    decision = client.decide('Show me cloud browsers.', observation, 'act')
    assert decision.action == 'open_docs' and decision.target is None
    assert client.last_raw == arguments
    assert client.last_raw['target'] == 4
    with pytest.raises(CoachProtocolError, match='requires act mode'):
        client.decide('Show me cloud browsers.', observation, 'guide')
