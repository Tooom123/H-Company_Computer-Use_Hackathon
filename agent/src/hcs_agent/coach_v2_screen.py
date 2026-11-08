"""H-only foreground observations and optional read-only account quota.

The old multi-product observer deliberately excludes settings pages. This one
allows the requested H workflows and sanitizes names before they can enter the
model context or private journal. Only named, non-secret fields in the observed
API-key/Skill creation forms may expose their values.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
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


@dataclass
class FormPage(a11y.PageInfo):
    form_kind: str | None = None
    form_fields: list[dict] = field(default_factory=list)


_FORM_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXPopUpButton"}
_FIELD_NAMES = {
    "api_key": {"name": "name", "key name": "name", "api key name": "name",
                "expiry": "expiry", "expiration": "expiry", "expiration date": "expiry",
                "expires": "expiry", "expires at": "expiry"},
    "skill": {"name": "name", "skill name": "name", "description": "description",
              "skill description": "description", "body": "body", "markdown": "body",
              "skill body": "body", "skill markdown": "body", "content": "body"},
}


def _field_name(label, kind):
    label = " ".join(str(label).strip().rstrip("*: ").casefold().split())
    return _FIELD_NAMES[kind].get(label)


def _form_kind(page):
    """Require both the exact H origin/path and a visible creation-form heading."""
    parsed = urlsplit(page.url)
    if parsed.hostname != "platform.hcompany.ai" or not readable_url(page.url):
        return None
    headings = [" ".join(c.name.casefold().split()) for c in page.elements if c.role == "AXHeading"]
    if re.search(r"(?:^|/)api[-_]?keys?(?:/|$)", parsed.path):
        if any(re.fullmatch(r"(?:create|new|add|generate)(?: an?| new)? api key", h) for h in headings):
            return "api_key"
    if re.search(r"(?:^|/)skills(?:/|$)", parsed.path):
        if any(re.fullmatch(r"(?:create|new|add)(?: an?| new)? skill", h) for h in headings):
            return "skill"
    return None


def _walk_form_inputs(web, viewport):
    """Include empty/unlabelled inputs omitted by the general label-only walker.

    One AX request per node; never request AXValue or descend into an editor.
    Semantic allowlisting happens before reading any field value.
    """
    import ApplicationServices as AS
    attrs = ["AXRole", "AXTitle", "AXDescription", "AXPlaceholderValue", "AXChildren", "AXFrame",
             "AXEnabled", "AXSelected"]
    result, stack, visited = [], [web], 0
    while stack and visited < 6000:
        ref, visited = stack.pop(), visited + 1
        error, values = AS.AXUIElementCopyMultipleAttributeValues(ref, attrs, 0, None)
        if error or values is None:
            continue
        role, title, description, placeholder, children, frame_value, enabled, selected = values
        if role not in a11y.INPUT_ROLES and children is not None and not isinstance(children, (str, int, float)):
            try:
                stack.extend(list(children))
            except TypeError:
                pass
        if role not in _FORM_ROLES or frame_value is None or isinstance(frame_value, (str, int, float)):
            continue
        ok, rect = AS.AXValueGetValue(frame_value, AS.kAXValueTypeCGRect, None)
        if not ok:
            continue
        frame = (float(rect.origin.x), float(rect.origin.y), float(rect.size.width), float(rect.size.height))
        if frame[2] < 2 or frame[3] < 2:
            continue
        if viewport:
            x, y, w, h = viewport
            if not (x <= frame[0] + frame[2] / 2 <= x + w and y <= frame[1] + frame[3] / 2 <= y + h):
                continue
        name = a11y._text(title) or a11y._text(description) or a11y._text(placeholder)
        result.append(a11y.Candidate(role, name, frame, ref=ref,
                                    enabled=a11y._boolean_state(enabled), selected=a11y._boolean_state(selected)))
    return result


def _field_candidate(candidate, page, kind):
    if _field_name(candidate.name, kind):
        return candidate
    # A genuinely named unrelated field (e.g. Source URL or a secret) never
    # acquires the name of its neighbour. Only missing names may be recovered.
    generic = {"text field", "text area", "text entry area", "edit text", "combo box"}
    if candidate.name.strip() and candidate.name.strip().casefold() not in generic:
        return None
    linked = a11y._attr(candidate.ref, "AXTitleUIElement")
    if linked is not None and a11y._attr(linked, "AXRole") in {"AXStaticText", "AXHeading"}:
        name = a11y._text(a11y._attr(linked, "AXTitle")) or a11y._text(a11y._attr(linked, "AXValue"))
        if _field_name(name, kind):
            return replace(candidate, name=name)
    x, y, width, _ = candidate.frame
    labels = [c for c in page.elements if c.role in {"AXStaticText", "AXHeading"}
              and _field_name(c.name, kind) and 0 <= y - c.frame[1] - c.frame[3] <= 60
              and abs(c.frame[0] - x) <= min(24, width / 4)]
    if len(labels) == 1:
        return replace(candidate, name=labels[0].name)
    return None


def _popup_value(candidate):
    own = a11y._attr(candidate.ref, "AXValue")
    if isinstance(own, str) and own.strip() and own.strip() != candidate.name.strip():
        return own
    # H's Expiry popup exposes the selected value as a static-text child.
    # Do not inspect the calendar/options popup elsewhere in the page.
    stack, labels = [(candidate.ref, 0)], []
    while stack and len(labels) < 5:
        ref, depth = stack.pop()
        children = a11y._attr(ref, "AXChildren")
        if children is None or isinstance(children, (str, int, float)):
            continue
        for child in list(children)[:15]:
            role = a11y._attr(child, "AXRole")
            if role == "AXStaticText":
                text = a11y._text(a11y._attr(child, "AXTitle")) or a11y._text(a11y._attr(child, "AXValue"))
                if text and text != candidate.name.strip():
                    labels.append(text)
            elif role == "AXGroup" and depth < 2:
                stack.append((child, depth + 1))
    labels = list(dict.fromkeys(labels))
    return labels[0] if len(labels) == 1 else None


def enrich_form_page(page, web):
    """Read only the creation form's allowlisted fields; never a generated key."""
    kind = _form_kind(page)
    if kind is None:
        return page
    candidates = _walk_form_inputs(web, page.viewport)
    fields, replacements = [], {}
    for original in candidates:
        if original.role not in _FORM_ROLES:
            continue
        candidate = _field_candidate(original, page, kind)
        if candidate is None or candidate.ref is None:
            continue
        name = _field_name(candidate.name, kind)
        value = _popup_value(candidate) if candidate.role == "AXPopUpButton" else a11y._attr(candidate.ref, "AXValue")
        if not isinstance(value, str):
            value = None
        if value is not None:
            value = public_text(value[:4000])
        fields.append({"field": name, "label": candidate.name, "value": value,
                       "redacted": value is not None and "[private " in value,
                       "box": list(candidate.box)})
        replacements[(candidate.role, candidate.box)] = candidate
    elements = [replacements.pop((c.role, c.box), c) for c in page.elements]
    elements.extend(replacements.values())
    return FormPage(**{**page.__dict__, "elements": elements}, form_kind=kind, form_fields=fields)


def observation_context(page, now=None):
    """A clock and observed form values; callers prepend text to the AX excerpt."""
    now = now or datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    clock = {"local_datetime": now.isoformat(timespec="seconds"), "timezone": now.tzname() or "local",
             "source": "local_system_clock"}
    fields = getattr(page, "form_fields", [])
    text = [f"Current local date and time: {clock['local_datetime']} ({clock['timezone']})."]
    for item in fields:
        value = item["value"]
        text.append(f"Observed {getattr(page, 'form_kind', '')} form field {item['label']}: "
                    + ("[value unavailable]" if value is None else repr(value)))
    return {"clock": clock, "form": {"kind": getattr(page, "form_kind", None), "fields": fields}, "text": text}


def verify_api_key_form(observation, requested_name, requested_hours=24, now=None):
    """Fail closed before creation: date-only expiry cannot prove exactly 24 h."""
    form = observation.get("form", {})
    if form.get("kind") != "api_key":
        return {"verified": False, "reason": "key_form_not_observed"}
    fields = form.get("fields", [])
    observed = {}
    for name in ("name", "expiry"):
        matches = [f for f in fields if f.get("field") == name]
        if len(matches) != 1 or matches[0].get("redacted") or not isinstance(matches[0].get("value"), str):
            return {"verified": False, "reason": f"{name}_not_observed"}
        observed[name] = matches[0]["value"].strip()
    if observed["name"] != requested_name:
        return {"verified": False, "reason": "name_mismatch", **observed}
    duration = re.fullmatch(r"(?:in\s+)?(\d+)\s*(hours?|hrs?|h|days?|d)", observed["expiry"], re.I)
    if duration:
        hours = int(duration[1]) * (24 if duration[2].casefold().startswith("d") else 1)
        return {"verified": hours == requested_hours,
                "reason": "observed_relative_duration" if hours == requested_hours else "expiry_duration_mismatch", **observed}
    if re.search(r"no expiry|never|none|unlimited", observed["expiry"], re.I):
        return {"verified": False, "reason": "no_expiry", **observed}
    # A date without a timezone-bearing time leaves expiry semantics unknown.
    if not re.search(r"[T ]\d{2}:\d{2}", observed["expiry"]):
        return {"verified": False, "reason": "date_only_cannot_verify_hours", **observed}
    try:
        expires = datetime.fromisoformat(observed["expiry"].replace("Z", "+00:00"))
        current = now or datetime.now().astimezone()
        if expires.tzinfo is None or current.tzinfo is None:
            raise ValueError("Unknown timezone")
        seconds = (expires - current).total_seconds()
    except ValueError:
        return {"verified": False, "reason": "expiry_time_not_verifiable", **observed}
    verified = abs(seconds - requested_hours * 3600) <= 60
    return {"verified": verified, "reason": "observed_expiry_time" if verified else "expiry_duration_mismatch", **observed}


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
    if page is not None:
        page = enrich_form_page(sanitize_page(page), web)
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
