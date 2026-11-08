"""H-only foreground observations and optional read-only account quota.

The old multi-product observer deliberately excludes settings pages. This one
allows the requested H workflows, never reads input values, and sanitizes names
before they can enter the model context or the private journal.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import os
import re
import threading
import time
from urllib.parse import parse_qsl, urlsplit

from . import a11y
from .coach_v2 import CoachProtocolError, allowed_page

# Exact known secret formats, JWTs and opaque high-entropy values. Long identifiers
# are hidden conservatively too; names and ordinary prose remain useful to the coach.
_SECRET = re.compile(
    r"\b(?:hk-|sk[-_]|sk_gladia_|AGE-SECRET-KEY-)[A-Za-z0-9_-]{8,}\b|"
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?\b|"
    r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{32,}(?![A-Za-z0-9])")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_SENSITIVE_QUERY = re.compile(r"token|secret|password|credential|api.?key|code", re.I)


def public_text(value: str) -> str:
    value = _SECRET.sub("[private value hidden]", str(value))
    return _CARD.sub("[private number hidden]", value)


def readable_url(url: str) -> bool:
    return allowed_page(url) and not any(_SENSITIVE_QUERY.search(key) for key, _ in parse_qsl(urlsplit(url).query))


def sanitize_page(page):
    """Pure boundary used before any observation is returned to the runtime."""
    if not page or not page.is_front or not readable_url(page.url):
        raise CoachProtocolError("Bring H Platform or its documentation to the front, then ask me again.",
                                 kind="observation", reason="outside_h_page")
    elements = []
    for candidate in page.elements:
        if candidate.role == "AXSecureTextField":
            continue
        name = public_text(candidate.name)
        # A secret itself is neither a grounding target nor useful page content.
        if "[private value hidden]" in name or "[private number hidden]" in name:
            continue
        elements.append(replace(candidate, name=name))
    return replace(page, title=public_text(page.title), elements=elements,
                   readable_text=tuple(public_text(text) for text in page.readable_text))


def read_page():
    """Read one H browser window; check its identity before and after collection."""
    if not a11y.available():
        raise CoachProtocolError("Accessibility access is unavailable.", kind="configuration", reason="accessibility_unavailable")
    bw = a11y._browser_window(front_only=True)
    if bw is None:
        raise CoachProtocolError("Bring H Platform or its documentation to the front, then ask me again.",
                                 kind="observation", reason="not_foreground")
    web = a11y._web_area(bw[0])
    url = str(a11y._attr(web, "AXURL") or "") if web is not None else ""
    if not readable_url(url):
        raise CoachProtocolError("Bring H Platform or its documentation to the front, then ask me again.",
                                 kind="observation", reason="outside_h_page")
    page = a11y._read_browser_page(bw, known_only=False)
    after = a11y._browser_window(front_only=True)
    after_web = a11y._web_area(after[0]) if after is not None else None
    after_url = str(a11y._attr(after_web, "AXURL") or "") if after_web is not None else ""
    if page is None or after is None or after[1] != bw[1] or page.url != after_url or url != after_url:
        raise CoachProtocolError("The active page changed during observation.", kind="observation", reason="page_changed")
    return sanitize_page(page)


_QUOTA_QUESTION = re.compile(r"concurr|parallel|simultan|at (?:the )?same time|at once|quota|"
                             r"how many.{0,50}(?:agents?|sessions?)|combien.{0,50}(?:agents?|sessions?)", re.I)
_quota_lock = threading.Lock()
_quota_cache = None
_quota_at = 0.0


def fetch_quota():
    """Read only the configured H account quota; no browser credentials are used."""
    import httpx
    base = os.environ.get("HAI_BASE_URL", "https://agp.eu.hcompany.ai").rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or parsed.hostname not in {"agp.eu.hcompany.ai", "agp.hcompany.ai"}
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or parsed.path not in {"", "/api/v2"}):
        return None
    key = os.environ.get("HAI_API_KEY") or os.environ.get("H_API_KEY")
    if not key:
        return None
    endpoint = base + ("" if parsed.path == "/api/v2" else "/api/v2") + "/sessions/quota"
    result = httpx.get(endpoint, headers={"Authorization": f"Bearer {key}"}, timeout=3)
    result.raise_for_status()
    raw = result.json()
    if not isinstance(raw, dict):
        return None
    fields = {}
    for field in ("limit", "active", "available"):
        value = raw.get(field)
        if value is not None and (type(value) is not int or value < 0):
            return None
        fields[field] = value
    if fields["limit"] is None and fields["active"] is None:
        return None
    if fields["available"] is None and fields["limit"] is not None and fields["active"] is not None:
        fields["available"] = max(0, fields["limit"] - fields["active"])
    return {**fields, "source": "H sessions quota API", "account": "configured_api_connection",
            "observed_at": datetime.now(timezone.utc).isoformat()}


def attach_quota(observation: dict, question: str) -> dict:
    global _quota_at, _quota_cache
    result = dict(observation)
    # No verified link exists between this API key and the browser account.
    # For "my current plan", the visible Billing page is the relevant evidence.
    # Supplying unrelated API numbers caused both attribution and limit/free-slot
    # confusion in real model probes, despite explicit prompting.
    api_connection_requested = re.search(r"\bcompanion\b.{0,40}\bapi\b|\bapi\b.{0,40}\bcompanion\b", question, re.I)
    if not _QUOTA_QUESTION.search(question) or not api_connection_requested:
        return result
    with _quota_lock:
        if time.monotonic() - _quota_at > 30 or _quota_at == 0:
            try:
                _quota_cache = fetch_quota()
            except Exception:
                _quota_cache = None
            _quota_at = time.monotonic()
        if _quota_cache is not None:
            result["account_quota"] = dict(_quota_cache)
    return result
