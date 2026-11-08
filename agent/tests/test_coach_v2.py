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


def envelope(decision):
    return {"choices": [{"message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {
                "name": "coach_step", "arguments": json.dumps(decision)}}]}}],
            "usage": {"prompt_tokens": 245, "completion_tokens": 51}}


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
    assert body["max_tokens"] == 320
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["temperature"] == 0
    tool = body["tools"][0]["function"]
    assert tool["strict"] is True
    assert tool["parameters"]["additionalProperties"] is False
    assert set(tool["parameters"]["required"]) == set(CoachDecision.model_fields)
    sent = json.loads(body["messages"][1]["content"])
    assert sent["mode"] == "guide"
    assert sent["question"] == "Give me a quick welcome tour of Orkney"
    assert sent["current_observation"]["text"] == observation["text"]
    assert client.last_raw == step()
    assert client.last_usage["completion_tokens"] == 51
    assert client.last_latency_s >= 0


@pytest.mark.parametrize("url", [
    "http://platform.hcompany.ai/agents", "https://platform.hcompany.ai.evil.example/",
    "https://platform.hcompany.ai@evil.example/", "https://user@platform.hcompany.ai/",
    "https://platform.hcompany.ai:444/", "https://platform.hcompany.ai/vaults",
    "https://platform.hcompany.ai/organisation/billing", "https://platform.hcompany.ai/%61pi-keys",
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
    assert "open_docs" not in requests[0]["tools"][0]["function"]["parameters"]["properties"]["action"]["enum"]
    assert "open_docs" in requests[1]["tools"][0]["function"]["parameters"]["properties"]["action"]["enum"]


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


@pytest.mark.parametrize("label", ["Delete session", "Vaults", "API keys", "Run", "Start agent", "Pay", "Upgrade"])
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


def test_typing_requires_a_text_input_and_single_line_literal(observation, client_factory):
    client, _ = client_factory(step(action="type", target=4, text="companion-demo"))
    assert client.decide("Find my demo", observation, "act").text == "companion-demo"
    client, _ = client_factory(step(action="type", target=1, text="companion-demo"))
    with pytest.raises(CoachProtocolError):
        client.decide("Find my demo", observation, "act")
    with pytest.raises(ValidationError):
        CoachDecision(**step(action="type", target=4, text="companion-demo\n"))


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
