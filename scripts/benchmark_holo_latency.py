#!/usr/bin/env python3
"""Compare OpenAI-compatible Holo streaming endpoints with one identical image request.

No screenshots are taken. Input bytes stay in memory; credentials come only from named
environment variables (optionally loaded from a private dotenv file). All requests are
sequential, connection-reusing, and explicitly requested by the person running the script.
The private JSON retains generated tool arguments for accuracy review, never a request
body, image, or authorization header. The public Markdown contains aggregate metrics only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit

import httpx


H_MODELS_BASE_URL = "https://api.hcompany.ai/v1"
NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,47}$")
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
POINT_TOOL = {"type": "function", "function": {
    "name": "locate", "description": "Locate the requested visible control in the supplied image.",
    "parameters": {"type": "object", "properties": {
        "x1": {"type": "integer"}, "y1": {"type": "integer"},
        "x2": {"type": "integer"}, "y2": {"type": "integer"},
        "is_the_control": {"type": "boolean"},
    }, "required": ["x1", "y1", "x2", "y2", "is_the_control"], "additionalProperties": False},
}}


class BenchmarkError(Exception):
    """Safe fixed error code, never a server response or a credential."""


@dataclass(frozen=True)
class Endpoint:
    name: str
    url: str
    auth_env: str | None = None

    @property
    def completion_url(self) -> str:
        return self.url.rstrip("/") + "/chat/completions"


def parse_assignment(value: str) -> tuple[str, str]:
    name, separator, setting = value.partition("=")
    if not separator or not NAME.fullmatch(name) or not setting:
        raise BenchmarkError("invalid_name_assignment")
    return name, setting


def endpoint_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise BenchmarkError("endpoint_requires_plain_base_url_without_credentials")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise BenchmarkError("unencrypted_endpoint_requires_loopback_proxy")
    if not parsed.path.rstrip("/").endswith("/v1"):
        raise BenchmarkError("endpoint_base_url_must_end_in_v1")
    return value.rstrip("/")


def load_image(path: Path) -> tuple[str, dict]:
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise BenchmarkError("image_missing_or_larger_than_16_mib")
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise BenchmarkError("image_must_be_png_jpeg_or_webp")
    metadata = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "mime": mime}
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii"), metadata


def make_payload(image_url: str, target: str, *, model: str, max_tokens: int, response_mode: str) -> dict:
    prompt = ("Locate this control in the supplied screenshot: " + target + ". "
              "Return its tight bounding box as integer x1,y1,x2,y2 normalized to [0,1000], "
              "and is_the_control=true only if that exact control is visible. "
              "If absent, use is_the_control=false and all four coordinates zero. "
              "Do not reason aloud or perform any action.")
    if response_mode == "json":
        prompt += " Return only one JSON object with these five fields."
    else:
        prompt += " Call the locate tool exactly once."
    payload = {"model": model, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image_url}}, {"type": "text", "text": prompt},
    ]}], "temperature": 0, "max_tokens": max_tokens, "stream": True,
        "stream_options": {"include_usage": True}, "chat_template_kwargs": {"enable_thinking": False}}
    if response_mode == "tools":
        payload.update(tools=[POINT_TOOL], tool_choice="required")
    return payload


def sse_events(lines: Iterable[str]) -> Iterable[str]:
    """Join standard multi-line data fields; ignore comments, event names and keepalives."""
    data: list[str] = []
    size = 0
    for line in lines:
        line = line.rstrip("\r\n")
        if not line:
            if data:
                yield "\n".join(data)
                data, size = [], 0
            continue
        if line.startswith("data:"):
            part = line[5:].removeprefix(" ")
            size += len(part)
            if size > 1024 * 1024:
                raise BenchmarkError("sse_event_too_large")
            data.append(part)
    if data:
        yield "\n".join(data)


def numeric_usage(value, depth: int = 0):
    """Retain numeric provider accounting, including nested cache details; drop free text."""
    if depth > 5:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    if isinstance(value, dict):
        return {key: clean for key, item in value.items()
                if isinstance(key, str) and re.fullmatch(r"[a-zA-Z0-9_]{1,80}", key)
                and (clean := numeric_usage(item, depth + 1)) is not None}
    return None


def usage_summary(raw: dict) -> dict:
    def number(*names):
        return next((raw[n] for n in names if isinstance(raw.get(n), (int, float))), None)

    cached = {}

    def collect(obj, prefix=""):
        for key, value in obj.items():
            name = prefix + key
            if isinstance(value, dict):
                collect(value, name + ".")
            elif "cache" in name.lower():
                cached[name] = value

    collect(raw)
    return {"input_tokens": number("prompt_tokens", "input_tokens"),
            "output_tokens": number("completion_tokens", "output_tokens"),
            "total_tokens": number("total_tokens"), "cache": cached, "provider_numeric": raw}


def point_result(text: str) -> dict | None:
    """Only retain bounded coordinates and presence, not generated prose or screen text."""
    try:
        result = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(result, dict) or type(result.get("is_the_control")) is not bool:
        return None
    if not all(type(result.get(key)) is int and 0 <= result[key] <= 1000 for key in ("x1", "y1", "x2", "y2")):
        return None
    if result["is_the_control"]:
        if result["x1"] >= result["x2"] or result["y1"] >= result["y2"]:
            return None
    elif any(result[key] != 0 for key in ("x1", "y1", "x2", "y2")):
        return None
    return {key: result[key] for key in ("x1", "y1", "x2", "y2", "is_the_control")}


class StreamMetrics:
    def __init__(self, response_mode="auto"):
        self.response_mode = response_mode
        self.ttft_ms = self.first_useful_ms = self.structured_result_ms = None
        self.first_token_kind = None
        self.done = False
        self.finish_reason = None
        self.events = []
        self.usage = {}
        self.text = ""
        self.arguments: dict[int, str] = {}
        self.tool_names: dict[int, str] = {}
        self.result = None

    def _delta(self, kind: str, text, elapsed_ms: float):
        if not isinstance(text, str) or not text.strip():
            return
        if self.ttft_ms is None:
            self.ttft_ms, self.first_token_kind = elapsed_ms, kind
        if kind in {"content", "tool_arguments"} and self.first_useful_ms is None:
            self.first_useful_ms = elapsed_ms
        self.events.append({"at_ms": elapsed_ms, "kind": kind, "characters": len(text)})

    def consume(self, data: str, elapsed_ms: float):
        if data.strip() == "[DONE]":
            self.done = True
            return
        try:
            event = json.loads(data)
        except ValueError:
            raise BenchmarkError("invalid_sse_json") from None
        if not isinstance(event, dict):
            raise BenchmarkError("invalid_sse_event")
        if event.get("error") is not None:
            raise BenchmarkError("provider_stream_error")
        if isinstance(event.get("usage"), dict):
            self.usage.update(numeric_usage(event["usage"]) or {})
        choices = event.get("choices") or []
        if not isinstance(choices, list):
            raise BenchmarkError("invalid_choices")
        for choice in choices:
            if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                continue
            reason = choice.get("finish_reason")
            if reason in {"stop", "length", "tool_calls", "function_call", "content_filter"}:
                self.finish_reason = reason
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                continue
            for field in ("reasoning_content", "reasoning"):
                self._delta("reasoning", delta.get(field), elapsed_ms)
            content = delta.get("content")
            self._delta("content", content, elapsed_ms)
            if isinstance(content, str):
                self.text += content
            calls = delta.get("tool_calls") or []
            if isinstance(delta.get("function_call"), dict):
                calls = [{"index": 0, "function": delta["function_call"]}]
            for call in calls if isinstance(calls, list) else []:
                if not isinstance(call, dict):
                    continue
                index, function = call.get("index", 0), call.get("function") or {}
                if type(index) is not int or not isinstance(function, dict):
                    continue
                self.tool_names.setdefault(index, "")
                name = function.get("name")
                if isinstance(name, str):
                    self.tool_names[index] += name
                arguments = function.get("arguments")
                self._delta("tool_arguments", arguments, elapsed_ms)
                if isinstance(arguments, str):
                    self.arguments[index] = self.arguments.get(index, "") + arguments
            if self.structured_result_ms is None:
                for candidate in [self.text, *self.arguments.values()]:
                    result = point_result(candidate)
                    if result is not None:
                        self.result, self.structured_result_ms = result, elapsed_ms
                        break

    def report(self) -> dict:
        # A transient valid prefix must not remain a valid result if later chunks corrupt it.
        if self.response_mode == "tools" or self.response_mode == "auto" and self.tool_names:
            final_result = None
            if len(self.tool_names) == 1:
                index, name = next(iter(self.tool_names.items()))
                if name == "locate":
                    final_result = point_result(self.arguments.get(index, ""))
        else:
            final_result = point_result(self.text)
        def private_completion(text):
            # Images can be echoed by a malfunctioning endpoint. Never persist a data URL.
            if "data:image/" in text.lower() or "base64," in text.lower():
                return "[omitted: image data in completion]"
            return text[:65536]
        return {"ttft_ms": self.ttft_ms, "first_token_kind": self.first_token_kind,
                "first_useful_ms": self.first_useful_ms,
                "structured_result_ms": self.structured_result_ms if final_result else None,
                "finish_reason": self.finish_reason, "done_marker": self.done,
                "final_structured_valid": final_result is not None,
                "usage": usage_summary(self.usage), "chunks": self.events, "grounding_result": final_result,
                "completion": {"content": private_completion(self.text),
                               "tool_arguments": {str(k): private_completion(v) for k, v in self.arguments.items()}}}


def measure(client: httpx.Client, endpoint: Endpoint, payload: dict, *, headers: dict,
            clock: Callable[[], float] = time.monotonic) -> dict:
    metrics = StreamMetrics(response_mode="tools" if payload.get("tools") else "json")
    result = {"endpoint": endpoint.name, "status": "ok", "error": None}
    started = clock()
    try:
        with client.stream("POST", endpoint.completion_url, json=payload, headers=headers) as response:
            result["headers_ms"] = round((clock() - started) * 1000, 3)
            result["http_status"] = response.status_code
            if response.status_code != 200:
                raise BenchmarkError(f"http_{response.status_code}")
            if "text/event-stream" not in response.headers.get("content-type", "").lower():
                raise BenchmarkError("response_is_not_sse")
            for data in sse_events(response.iter_lines()):
                metrics.consume(data, round((clock() - started) * 1000, 3))
                if metrics.done:
                    break
        if not metrics.done and metrics.finish_reason is None:
            raise BenchmarkError("incomplete_stream")
        if metrics.finish_reason == "length":
            raise BenchmarkError("output_truncated")
        if metrics.finish_reason == "content_filter":
            raise BenchmarkError("content_filtered")
        if metrics.first_useful_ms is None:
            raise BenchmarkError("no_useful_output")
        if not metrics.report()["final_structured_valid"]:
            raise BenchmarkError("invalid_structured_output")
    except BenchmarkError as exc:
        result.update(status="error", error=str(exc))
    except httpx.TimeoutException:
        result.update(status="error", error="transport_timeout")
    except httpx.HTTPError:
        result.update(status="error", error="transport_error")
    except (ValueError, TypeError, UnicodeError):
        result.update(status="error", error="malformed_response")
    result.update(metrics.report(), total_ms=round((clock() - started) * 1000, 3))
    return result


def distribution(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "median": None, "p95": None, "min": None, "max": None}
    values = sorted(values)
    location = (len(values) - 1) * 0.95
    lower, upper = math.floor(location), math.ceil(location)
    p95 = values[lower] + (values[upper] - values[lower]) * (location - lower)
    return {"n": len(values), "median": round(statistics.median(values), 3), "p95": round(p95, 3),
            "min": min(values), "max": max(values)}


def summarize(records: list[dict]) -> dict:
    result = {}
    for name in dict.fromkeys(r["endpoint"] for r in records):
        trials = [r for r in records if r["endpoint"] == name and not r["warmup"]]
        valid = [r for r in trials if r["status"] == "ok"]
        metrics = {key: distribution([r[key] for r in valid if r.get(key) is not None]) for key in (
            "ttft_ms", "first_useful_ms", "structured_result_ms", "total_ms")}
        usage = {key: distribution([r["usage"][key] for r in valid if r["usage"].get(key) is not None])
                 for key in ("input_tokens", "output_tokens", "total_tokens")}
        errors = {}
        for r in trials:
            if r["error"]:
                errors[r["error"]] = errors.get(r["error"], 0) + 1
        result[name] = {"trials": len(trials), "ok": len(valid), "errors": errors, "metrics": metrics,
                        "usage": usage, "cache_observed": [r["usage"]["cache"] for r in valid],
                        "structured_results": sum(r["grounding_result"] is not None for r in valid)}
    return result


def markdown_report(report: dict) -> str:
    def fmt(value):
        return "non exposé" if value is None else f"{value:.1f}"
    label = report["image"]["label"].replace("\n", " ").replace("|", "/")
    lines = ["# Holo — latence du flux HTTP", "", f"Image : **{label}** · modèle demandé : `{report['model']}`.",
             "", "Mesures réelles de ce script uniquement ; chaque endpoint reçoit les mêmes octets et le même prompt.",
             "Les échauffements sont exclus ; connexions persistantes et ordre alterné entre les rounds.", "",
             "| Endpoint | Réponses structurées / essais | TTFT médian / p95 (ms) | Contenu utile médian (ms) | JSON complet médian (ms) | Total médian / p95 (ms) | Tokens entrée / sortie médians |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, summary in report["summary"].items():
        m, u = summary["metrics"], summary["usage"]
        lines.append(f"| {name} | {summary['ok']}/{summary['trials']} | {fmt(m['ttft_ms']['median'])} / {fmt(m['ttft_ms']['p95'])} | "
                     f"{fmt(m['first_useful_ms']['median'])} | {fmt(m['structured_result_ms']['median'])} | "
                     f"{fmt(m['total_ms']['median'])} / {fmt(m['total_ms']['p95'])} | "
                     f"{fmt(u['input_tokens']['median'])} / {fmt(u['output_tokens']['median'])} |")
    for name, summary in report["summary"].items():
        if summary["errors"]:
            lines.extend(["", f"Erreurs {name} : " + ", ".join(f"{k} × {v}" for k, v in summary["errors"].items()) + "."])
    lines.extend(["", "- TTFT : premier fragment non vide de contenu, raisonnement ou arguments d’outil ; le type est conservé dans le JSON privé. Un rôle vide ou un nom d’outil seul ne compte pas.",
                  "- Contenu utile : premier fragment de contenu ou d’arguments, même incomplet. « JSON complet » exige les cinq champs de localisation valides ; cela ne prouve pas que la cible est correcte.",
                  "- Les tokens et détails de cache sont ceux du fournisseur, jamais des estimations. Un champ absent reste inconnu. Le même écran répété peut bénéficier du cache.",
                  "- Durées client : réseau, proxy/tunnel, attente, préremplissage et génération inclus ; ce n’est pas un benchmark GPU isolé ni celui de l’app complète.",
                  "- Température 0, thinking désactivé, mais aucune garantie de déterminisme. Le même identifiant de modèle ne garantit pas la même quantification ni la même infrastructure.",
                  "- Avec peu d’essais, le p95 est une statistique descriptive interpolée, pas une garantie de service.",
                  "", "Aucune image, clé, réponse textuelle brute ou URL privée dans ce résumé.", ""])
    return "\n".join(lines)


def write_private(path: Path, content: str):
    # Refuse overwrite/symlinks and never briefly create a world-readable result.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--image-label", required=True, help="Public non-sensitive fixture label")
    parser.add_argument("--target", required=True, help="Same visible control to locate at all endpoints")
    parser.add_argument("--endpoint", action="append", required=True, metavar="NAME=BASE_URL")
    parser.add_argument("--auth-env", action="append", default=[], metavar="NAME=ENV_VARIABLE")
    parser.add_argument("--no-auth", action="append", default=[], metavar="NAME", help="Explicit local auth-injecting proxy")
    parser.add_argument("--env-file", type=Path, help="Optional private dotenv file; never printed")
    parser.add_argument("--model", default="holo4-35b-a3b")
    parser.add_argument("--response-mode", choices=("tools", "json"), default="tools")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output-dir", type=Path, required=True, help="New private directory, must not exist")
    args = parser.parse_args(argv)
    clients = {}
    try:
        if not (1 <= args.trials <= 50 and 0 <= args.warmups <= 5 and 16 <= args.max_tokens <= 1024
                and 1 <= args.timeout <= 600 and 1 <= len(args.image_label) <= 80
                and 1 <= len(args.target) <= 2000):
            raise BenchmarkError("invalid_benchmark_bounds")
        auth = dict(parse_assignment(v) for v in args.auth_env)
        endpoints = [Endpoint(name, endpoint_url(url), auth.get(name)) for name, url in map(parse_assignment, args.endpoint)]
        names = {e.name for e in endpoints}
        if len(names) != len(endpoints) or not set(auth).issubset(names) or not set(args.no_auth).issubset(names):
            raise BenchmarkError("duplicate_or_unknown_endpoint")
        credentials = dict(os.environ)
        if args.env_file:
            from dotenv import dotenv_values
            credentials = {**dotenv_values(args.env_file, interpolate=False), **credentials}
        headers = {}
        for endpoint in endpoints:
            if endpoint.auth_env:
                if endpoint.name in args.no_auth or not ENV_NAME.fullmatch(endpoint.auth_env):
                    raise BenchmarkError("invalid_or_conflicting_auth_configuration")
                key = credentials.get(endpoint.auth_env)
                if not key or "\n" in key or "\r" in key:
                    raise BenchmarkError("missing_or_invalid_auth_environment_variable")
                headers[endpoint.name] = {"Authorization": "Bearer " + key}
            elif endpoint.name in args.no_auth and urlsplit(endpoint.url).hostname in {"localhost", "127.0.0.1", "::1"}:
                headers[endpoint.name] = {}
            else:
                raise BenchmarkError("endpoint_requires_auth_env_or_explicit_local_proxy")
        image_url, image_metadata = load_image(args.image)
        payload = make_payload(image_url, args.target, model=args.model, max_tokens=args.max_tokens,
                               response_mode=args.response_mode)
        args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "simulated": False,
                  "model": args.model, "response_mode": args.response_mode, "max_tokens": args.max_tokens,
                  "thinking": False, "temperature": 0, "trials": args.trials, "warmups": args.warmups,
                  "image": {**image_metadata, "label": args.image_label},
                  "prompt_sha256": hashlib.sha256(payload["messages"][0]["content"][1]["text"].encode()).hexdigest(),
                  "endpoints": [{"name": e.name, "base_url": e.url} for e in endpoints], "records": []}
        for endpoint in endpoints:
            clients[endpoint.name] = httpx.Client(timeout=httpx.Timeout(args.timeout, connect=10),
                                                 follow_redirects=False, trust_env=False)
        for warmup, rounds in ((True, args.warmups), (False, args.trials)):
            for index in range(rounds):
                order = endpoints if index % 2 == 0 else list(reversed(endpoints))
                for endpoint in order:
                    record = measure(clients[endpoint.name], endpoint, payload, headers=headers[endpoint.name])
                    record.update(warmup=warmup, round=index + 1)
                    report["records"].append(record)
                    print(f"{endpoint.name}: {'warmup' if warmup else 'trial'} {index + 1}/{rounds} {record['status']}", flush=True)
        report["summary"] = summarize(report["records"])
        write_private(args.output_dir / "results.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        write_private(args.output_dir / "summary.md", markdown_report(report))
        print("Saved private results.json and shareable summary.md in the requested output directory.")
        return 0 if all(r["status"] == "ok" for r in report["records"] if not r["warmup"]) else 2
    except BenchmarkError as exc:
        print(f"Benchmark refused: {exc}", file=__import__("sys").stderr)
        return 2
    except (OSError, ImportError, ValueError):
        print("Benchmark setup/output unavailable; check private paths and httpx/python-dotenv dependencies.", file=__import__("sys").stderr)
        return 2
    finally:
        for client in clients.values():
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
