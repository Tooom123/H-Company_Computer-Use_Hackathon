"""Offline streaming transport, accounting, and disclosure tests for the benchmark."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import httpx
import pytest


SPEC = importlib.util.spec_from_file_location("benchmark_holo_latency", Path(__file__).with_name("benchmark_holo_latency.py"))
bench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bench
SPEC.loader.exec_module(bench)
POINT = {"x1": 100, "y1": 200, "x2": 300, "y2": 400, "is_the_control": True}


def delta(fields, *, finish=None):
    return json.dumps({"choices": [{"index": 0, "delta": fields, "finish_reason": finish}]})


def encoded_sse(*events):
    return "".join(f"data: {item}\n\n" for item in events).encode()


def test_sse_supports_comments_crlf_multiline_and_eof_event():
    lines = [": keepalive\r\n", "event: message", 'data: {"choices":', 'data: []}', "", "data: [DONE]"]
    assert list(bench.sse_events(lines)) == ['{"choices":\n[]}', "[DONE]"]


def test_empty_role_and_tool_name_are_not_tokens():
    metrics = bench.StreamMetrics()
    metrics.consume(delta({"role": "assistant", "content": ""}), 5)
    metrics.consume(delta({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "locate", "arguments": ""}}]}), 10)
    assert metrics.report()["ttft_ms"] is None
    metrics.consume(delta({"tool_calls": [{"index": 0, "function": {"arguments": "{"}}]}), 20)
    assert metrics.report()["ttft_ms"] == 20
    assert metrics.report()["first_useful_ms"] == 20
    assert metrics.report()["first_token_kind"] == "tool_arguments"


def test_reasoning_counts_for_ttft_but_not_first_useful():
    metrics = bench.StreamMetrics()
    metrics.consume(delta({"reasoning_content": "Let me inspect"}), 10)
    metrics.consume(delta({"content": " "}), 20)
    assert metrics.report()["first_useful_ms"] is None
    metrics.consume(delta({"content": json.dumps(POINT)}), 30)
    report = metrics.report()
    assert report["ttft_ms"] == 10 and report["first_token_kind"] == "reasoning"
    assert report["first_useful_ms"] == report["structured_result_ms"] == 30
    assert "Let me inspect" not in json.dumps(report)  # no chain-of-thought persisted


def test_incremental_tool_arguments_preserve_accuracy_without_image_payload():
    metrics = bench.StreamMetrics()
    text = json.dumps(POINT)
    metrics.consume(delta({"tool_calls": [{"index": 0, "function": {"name": "locate", "arguments": text[:12]}}]}), 20)
    metrics.consume(delta({"tool_calls": [{"index": 0, "function": {"arguments": text[12:]}}]}, finish="tool_calls"), 30)
    metrics.consume("[DONE]", 31)
    report = metrics.report()
    assert report["structured_result_ms"] == 30 and report["grounding_result"] == POINT
    assert json.loads(report["completion"]["tool_arguments"]["0"]) == POINT
    assert report["done_marker"] is True and report["finish_reason"] == "tool_calls"


def test_final_garbage_invalidates_transient_complete_json():
    metrics = bench.StreamMetrics()
    metrics.consume(delta({"content": json.dumps(POINT)}), 10)
    metrics.consume(delta({"content": "bad suffix"}), 20)
    assert metrics.report()["grounding_result"] is None
    assert metrics.report()["structured_result_ms"] is None


@pytest.mark.parametrize("name,second_call,expected", [("locate", False, True), ("other", False, False),
                                                       ("locate", True, False), ("", False, False)])
def test_tools_require_exactly_one_named_locate_call(name, second_call, expected):
    metrics = bench.StreamMetrics(response_mode="tools")
    calls = [{"index": 0, "function": {"name": name, "arguments": json.dumps(POINT)}}]
    if second_call:
        calls.append({"index": 1, "function": {"name": "locate", "arguments": json.dumps(POINT)}})
    metrics.consume(delta({"tool_calls": calls}, finish="tool_calls"), 10)
    assert metrics.report()["final_structured_valid"] is expected


@pytest.mark.parametrize("point", [{**POINT, "x2": 100}, {**POINT, "is_the_control": False}])
def test_grounding_requires_positive_box_or_explicit_absent_zero_coordinates(point):
    assert bench.point_result(json.dumps(point)) is None


@pytest.mark.parametrize("finish,error", [("length", "output_truncated"), ("content_filter", "content_filtered")])
def test_finish_reason_failure_is_not_hidden_by_a_parseable_prefix(finish, error):
    result, _ = measured_response(encoded_sse(delta({"content": json.dumps(POINT)}, finish=finish), "[DONE]"))
    assert result["status"] == "error" and result["error"] == error


def test_provider_usage_keeps_nested_cache_without_estimation_or_free_text():
    metrics = bench.StreamMetrics()
    metrics.consume(json.dumps({"choices": [], "usage": {
        "prompt_tokens": 123, "completion_tokens": 12, "total_tokens": 135,
        "prompt_tokens_details": {"cached_tokens": 80},
        "completion_tokens_details": {"reasoning_tokens": 2},
        "cache_read_input_tokens": 80, "private_text": "NEVER_SAVE_THIS",
    }}), 5)
    usage = metrics.report()["usage"]
    assert usage["input_tokens"] == 123 and usage["output_tokens"] == 12 and usage["total_tokens"] == 135
    assert usage["cache"] == {"prompt_tokens_details.cached_tokens": 80, "cache_read_input_tokens": 80}
    assert usage["provider_numeric"]["completion_tokens_details"] == {"reasoning_tokens": 2}
    assert "NEVER_SAVE_THIS" not in json.dumps(usage)
    missing = bench.StreamMetrics().report()["usage"]
    assert missing["input_tokens"] is None and missing["total_tokens"] is None and missing["cache"] == {}


@pytest.mark.parametrize("event,code", [('not-json', "invalid_sse_json"),
                                      ('{"error":{"message":"SENSITIVE_ERROR"}}', "provider_stream_error"),
                                      ('[]', "invalid_sse_event")])
def test_sse_errors_use_fixed_codes_without_provider_details(event, code):
    with pytest.raises(bench.BenchmarkError, match=code):
        bench.StreamMetrics().consume(event, 5)


def measured_response(body, *, code=200, mime="text/event-stream"):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(code, content=body, headers={"content-type": mime})

    times = iter(i / 10 for i in range(100))
    payload = bench.make_payload("data:image/png;base64,PRIVATE_IMAGE", "Button", model="holo4-35b-a3b",
                                 max_tokens=128, response_mode="json")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = bench.measure(client, bench.Endpoint("cloud", bench.H_MODELS_BASE_URL), payload,
                               headers={"Authorization": "Bearer SECRET_AUTH"}, clock=lambda: next(times))
    return result, requests


def test_http_measure_handles_usage_only_tail_and_excludes_secrets():
    result, requests = measured_response(encoded_sse(
        delta({"role": "assistant"}), delta({"content": json.dumps(POINT)}, finish="stop"),
        json.dumps({"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}), "[DONE]"))
    assert result["status"] == "ok" and result["total_ms"] > result["ttft_ms"] > result["headers_ms"]
    assert result["usage"]["input_tokens"] == 10
    assert requests[0].headers["authorization"] == "Bearer SECRET_AUTH"
    assert "SECRET_AUTH" not in json.dumps(result) and "PRIVATE_IMAGE" not in json.dumps(result)


@pytest.mark.parametrize("body,code,mime,error", [
    (b"SECRET_AUTH PRIVATE_IMAGE", 401, "application/json", "http_401"),
    (b"not streaming", 200, "application/json", "response_is_not_sse"),
    (encoded_sse(delta({"content": "{"})), 200, "text/event-stream", "incomplete_stream"),
    (encoded_sse(delta({"reasoning": "hidden"}, finish="stop"), "[DONE]"), 200, "text/event-stream", "no_useful_output"),
    (encoded_sse('{"error":{"message":"SECRET_AUTH"}}'), 200, "text/event-stream", "provider_stream_error"),
])
def test_stream_failures_stay_failed_and_never_echo_server_body(body, code, mime, error):
    result, _ = measured_response(body, code=code, mime=mime)
    assert result["status"] == "error" and result["error"] == error
    assert "SECRET_AUTH" not in json.dumps(result)


def test_timeout_retains_safe_error_code():
    def handler(request):
        raise httpx.ReadTimeout("could include sensitive address")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = bench.measure(client, bench.Endpoint("dgx", "http://127.0.0.1:18013/v1"), {}, headers={})
    assert result["error"] == "transport_timeout" and "sensitive" not in json.dumps(result)


def test_echoed_image_is_not_saved_as_completion():
    metrics = bench.StreamMetrics()
    metrics.consume(delta({"content": "data:image/png;base64,PRIVATE_IMAGE"}), 5)
    assert "PRIVATE_IMAGE" not in json.dumps(metrics.report())


@pytest.mark.parametrize("url", ["https://key:secret@example.com/v1", "https://example.com/v1?key=secret",
                                 "http://remote.example/v1", "https://example.com/v1/chat/completions"])
def test_endpoint_configuration_refuses_embedded_credentials_or_plain_remote_http(url):
    with pytest.raises(bench.BenchmarkError):
        bench.endpoint_url(url)


def test_payload_is_deterministically_requested_and_identical_for_both_transports():
    payload = bench.make_payload("data:image/png;base64,FIXTURE", "Connexion", model="holo4-35b-a3b",
                                 max_tokens=128, response_mode="tools")
    assert payload["temperature"] == 0 and payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["stream_options"] == {"include_usage": True} and payload["max_tokens"] == 128
    assert payload["tool_choice"] == "required"
    assert payload["tools"][0]["function"]["name"] == "locate"


def test_cli_alternates_endpoints_excludes_warmups_and_writes_private_results(tmp_path, monkeypatch, capsys):
    image = tmp_path / "fixture.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nTEST_PRIVATE_IMAGE")
    env = tmp_path / "private.env"
    env.write_text("BENCH_TEST_H=cloud-secret\nBENCH_TEST_DGX=wrong-file-secret\n")
    monkeypatch.setenv("BENCH_TEST_DGX", "inherited-proxy-secret")
    monkeypatch.delenv("BENCH_TEST_H", raising=False)
    calls = []
    client_class = httpx.Client

    def handler(request):
        calls.append((str(request.url), request.headers["authorization"], json.loads(request.content)))
        return httpx.Response(200, content=encoded_sse(delta({"tool_calls": [{"index": 0, "function": {"name": "locate", "arguments": json.dumps(POINT)}}]}, finish="tool_calls"), "[DONE]"),
                              headers={"content-type": "text/event-stream"})

    monkeypatch.setattr(bench.httpx, "Client", lambda **options: client_class(transport=httpx.MockTransport(handler)))
    output = tmp_path / "new-private-results"
    args = ["--image", str(image), "--image-label", "public-fixture", "--target", "Button",
            "--endpoint", "cloud=https://api.hcompany.ai/v1", "--endpoint", "dgx=http://127.0.0.1:18013/v1",
            "--auth-env", "cloud=BENCH_TEST_H", "--auth-env", "dgx=BENCH_TEST_DGX", "--env-file", str(env),
            "--trials", "2", "--warmups", "1", "--output-dir", str(output)]
    assert bench.main(args) == 0
    assert ["cloud" if "hcompany" in url else "dgx" for url, _, _ in calls] == ["cloud", "dgx", "cloud", "dgx", "dgx", "cloud"]
    assert {header for _, header, _ in calls} == {"Bearer cloud-secret", "Bearer inherited-proxy-secret"}
    assert all(payload == calls[0][2] for _, _, payload in calls)
    report_text = (output / "results.json").read_text()
    report = json.loads(report_text)
    assert len(report["records"]) == 6 and report["summary"]["cloud"]["trials"] == 2
    assert report["summary"]["cloud"]["usage"]["input_tokens"]["n"] == 0
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / "results.json").stat().st_mode & 0o777 == 0o600
    public = (output / "summary.md").read_text()
    logs = capsys.readouterr().out
    for private in ("cloud-secret", "inherited-proxy-secret", "TEST_PRIVATE_IMAGE", "base64,"):
        assert private not in report_text + public + logs
    assert "127.0.0.1" not in public and "http" not in public.lower().replace("http", "", 1)
    assert '"x1"' not in public
    assert bench.main(args) == 2  # refuses overwriting previous benchmark evidence
    assert len(calls) == 6


def test_private_write_refuses_existing_symlink(tmp_path):
    actual = tmp_path / "existing"
    actual.write_text("untouched")
    link = tmp_path / "link"
    link.symlink_to(actual)
    with pytest.raises(FileExistsError):
        bench.write_private(link, "new")
    assert actual.read_text() == "untouched"
