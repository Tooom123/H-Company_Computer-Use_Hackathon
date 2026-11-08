"""A cached narration may avoid Holo, but never substitute stale UI evidence."""
import json
import stat

import pytest

from hcs_agent import coach_v2_tour_cache as cache_module
from hcs_agent.coach_v2 import CoachDecision
from hcs_agent.coach_v2_tour_cache import TourCache, generic_tour_requested


QUESTION = "Hey Companion, I'm new here. Can you give me a quick tour?"
FINGERPRINT = "holo4-35b-a3b\nsystem-prompt-v1\nproduct-knowledge-v1"


def observation(*, offset=0, shift=0):
    return {
        "url": "https://platform.hcompany.ai/agents/sessions",
        "viewport": [shift, 100, 1440, 900],
        "title": "Private organization name",
        "text": ["Private page text must not be persisted."],
        "controls": [
            {"id": index + offset, "label": label, "role": "AXButton", "enabled": True,
             "box": [shift + 24, 250 + index * 50, 210, 40]}
            for index, label in enumerate(("Agents", "Sessions", "Skills"), 1)
        ],
    }


def decision():
    return CoachDecision.model_validate({
        "action": "tour", "speech": "Welcome to H Platform. Let me show you around.",
        "points": [
            {"target": 1, "speech": "Agents is where you configure your assistants."},
            {"target": 2, "speech": "Sessions contains your runs and their answers."},
            {"target": 3, "speech": "Skills gives your agents reusable instructions."},
        ],
    })


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module.time, "time", lambda: 1000.0)
    return TourCache(tmp_path / "private" / "tour-cache.json", FINGERPRINT)


@pytest.mark.parametrize("question", [
    QUESTION,
    "Hey companion, I'm new here, give me a quick tour?",
    "Can you show me around?",
    "Show me around H Platform, please.",
    "Give me a quick welcome tour of H Platform.",
    "Quick tour",
    "Hello, I’m new to this platform. Could you show me a brief tour?",
])
def test_generic_welcome_requests_are_cacheable(question):
    assert generic_tour_requested(question)


@pytest.mark.parametrize("question", [
    "Show me around API keys.",
    "Give me a quick tour of new features.",
    "Give me a quick tour and create an API key.",
    "Don't give me a quick tour.",
    "How can I launch an agent?",
    "Create a skill that gives users a quick tour.",
    "Show me the Sessions section.",
    "Give me a quick tour of Odoo.",
    "What did you say in the quick tour?",
    "Give me a tour of this error.",
])
def test_targeted_or_mixed_requests_never_match_generic_tour(question):
    assert not generic_tour_requested(question)


def test_cache_remaps_ids_on_a_fresh_moved_window(cache):
    assert cache.put(QUESTION, decision(), observation(), "act")
    fresh = observation(offset=100, shift=400)
    result = cache.get("Can you show me around?", fresh, "act")
    assert result.action == "tour"
    assert [point.target for point in result.points] == [101, 102, 103]
    assert result.speech == decision().speech


def test_cache_is_mode_specific_and_persists_across_instances(cache):
    assert cache.put(QUESTION, decision(), observation(), "act")
    assert cache.get(QUESTION, observation(), "guide") is None
    assert cache.put(QUESTION, decision(), observation(), "guide")
    reloaded = TourCache(cache.path, FINGERPRINT)
    assert reloaded.get(QUESTION, observation(), "act") is not None
    assert reloaded.get(QUESTION, observation(), "guide") is not None


def test_cache_file_contains_only_metadata_narration_and_control_names(cache):
    assert cache.put(QUESTION, decision(), observation(), "act")
    data = json.loads(cache.path.read_text())
    assert set(data) == {"version", "fingerprint", "entries"}
    assert set(data["entries"]["act"]) == {"saved_at", "speech", "points"}
    assert all(set(point) == {"label", "role", "speech"} for point in data["entries"]["act"]["points"])
    text = cache.path.read_text()
    assert "Private" not in text and "viewport" not in text and '"box"' not in text
    assert '"target"' not in text and '"id"' not in text and QUESTION not in text
    assert FINGERPRINT not in text
    assert stat.S_IMODE(cache.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(cache.path.parent.stat().st_mode) == 0o700


def test_same_label_in_body_does_not_override_sidebar(cache):
    assert cache.put(QUESTION, decision(), observation(), "act")
    fresh = observation(offset=10)
    fresh["controls"].append({"id": 99, "label": "Agents", "role": "AXButton",
                              "box": [464, 170, 89, 24], "enabled": True})
    result = cache.get(QUESTION, fresh, "act")
    assert result.points[0].target == 11


@pytest.mark.parametrize("mutation", [
    lambda obs: obs.pop("viewport"),
    lambda obs: obs["controls"].pop(),
    lambda obs: obs["controls"][0].update(enabled=False),
    lambda obs: obs["controls"][0].update(role="AXLink"),
    lambda obs: obs["controls"][0].update(box=[24, 3000, 210, 40]),
    lambda obs: obs["controls"][0].update(box=[float("nan"), 300, 210, 40]),
    lambda obs: obs["controls"].append(dict(obs["controls"][0], id=99)),
    lambda obs: obs["controls"][0].update(id=2),
    lambda obs: obs["controls"][0].update(label=[]),
    lambda obs: obs.update(url="https://hub.hcompany.ai/agents-api/overview"),
    lambda obs: obs.update(url="https://platform.hcompany.ai/auth/login"),
    lambda obs: obs.update(url="https://platform.hcompany.ai.evil.example/agents"),
])
def test_missing_ambiguous_disabled_or_changed_ui_is_cache_miss(cache, mutation):
    assert cache.put(QUESTION, decision(), observation(), "act")
    fresh = observation()
    mutation(fresh)
    assert cache.get(QUESTION, fresh, "act") is None


def test_put_refuses_a_model_target_outside_sidebar(cache):
    page = observation()
    page["controls"].append({"id": 99, "label": "Agents", "role": "AXButton",
                             "box": [464, 170, 89, 24], "enabled": True})
    wrong = decision().model_copy(deep=True)
    wrong.points[0].target = 99
    assert not cache.put(QUESTION, wrong, page, "act")
    assert not cache.path.exists()


def test_changed_prompt_or_model_fingerprint_invalidates_cache(cache):
    assert cache.put(QUESTION, decision(), observation(), "act")
    assert TourCache(cache.path, FINGERPRINT + "changed").get(QUESTION, observation(), "act") is None


@pytest.mark.parametrize("now", [999, 1000 + cache_module.TTL_SECONDS, 1000 + cache_module.TTL_SECONDS + 1])
def test_expired_or_future_cache_is_missed(cache, monkeypatch, now):
    assert cache.put(QUESTION, decision(), observation(), "act")
    monkeypatch.setattr(cache_module.time, "time", lambda: now)
    assert cache.get(QUESTION, observation(), "act") is None


def test_live_cache_is_valid_before_ttl(cache, monkeypatch):
    assert cache.put(QUESTION, decision(), observation(), "act")
    monkeypatch.setattr(cache_module.time, "time", lambda: 1000 + cache_module.TTL_SECONDS - 1)
    assert cache.get(QUESTION, observation(), "act") is not None


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(version=999),
    lambda data: data["entries"]["act"].update(speech="Result: Done"),
    lambda data: data["entries"]["act"]["points"][0].update(speech="```python\nprint('hello')\n```"),
    lambda data: data["entries"]["act"]["points"][0].update(label="Create API key"),
    lambda data: data["entries"]["act"].update(saved_at="yesterday"),
    lambda data: data["entries"]["act"].update(points=[]),
])
def test_malformed_or_unreadable_cached_speech_is_rejected(cache, mutation):
    assert cache.put(QUESTION, decision(), observation(), "act")
    data = json.loads(cache.path.read_text())
    mutation(data)
    cache.path.write_text(json.dumps(data))
    assert cache.get(QUESTION, observation(), "act") is None


def test_cache_refuses_public_file_or_symlink(cache, tmp_path):
    assert cache.put(QUESTION, decision(), observation(), "act")
    cache.path.chmod(0o644)
    assert cache.get(QUESTION, observation(), "act") is None
    cache.path.chmod(0o600)
    alias = tmp_path / "cache-link.json"
    alias.symlink_to(cache.path)
    linked = TourCache(alias, FINGERPRINT)
    assert linked.get(QUESTION, observation(), "act") is None
    assert not linked.put(QUESTION, decision(), observation(), "act")


def test_io_failures_are_cache_misses_not_request_failures(cache, monkeypatch):
    def unavailable(*args, **kwargs):
        raise PermissionError("No write permission")
    monkeypatch.setattr(cache_module.os, "open", unavailable)
    assert cache.get(QUESTION, observation(), "act") is None
    assert not cache.put(QUESTION, decision(), observation(), "act")


def test_non_tour_decisions_and_non_generic_questions_are_not_saved(cache):
    click = CoachDecision(action="click", target=1, speech="Open Agents.")
    assert not cache.put(QUESTION, click, observation(), "act")
    assert not cache.put("Give me a quick tour of new features", decision(), observation(), "act")
    assert not cache.path.exists()
