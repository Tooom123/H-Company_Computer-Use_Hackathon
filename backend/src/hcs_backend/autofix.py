"""Auto-fix: when a case points at a suspected product defect, ask Devin (Cognition) to reproduce it, fix it
and open a pull request on the vendor's repository; the PR link comes back into the support dashboard.

Safety rails
- Only repositories on the allowlist (`HCS_FIX_REPOS`, software name -> owner/repo) are ever targeted.
- Automatic trigger only for cases categorised `suspected_product_defect` (and only when `HCS_FIX_AUTO=1`);
  support can trigger it by hand for any case whose software is on the allowlist.
- One fix request per case; an ACU cap per session (`HCS_FIX_MAX_ACU`).
- Without Devin credentials, a simulated provider runs the same flow (flagged `simulated`).

Devin API v3: POST /v3/organizations/{org_id}/sessions, GET /v3/organizations/{org_id}/sessions/{devin_id};
the session exposes `status` (new, claimed, running, exit, error, suspended, resuming), `url`,
`pull_requests[].pr_url / pr_state` and `structured_output`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .announce import Announcer, fix_lines
from .escalation import build_escalation
from .store import StoredCase

TERMINAL = {"exit", "error"}


def is_done(fix: dict[str, Any]) -> bool:
    """Finished: the session ended, or Devin opened its PR and is now just waiting for feedback
    (observed on real runs: status stays running / waiting_for_user after the PR)."""
    return fix.get("status") in TERMINAL or (bool(fix.get("pr_url")) and fix.get("status_detail") == "waiting_for_user")

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "reproduced": {"type": "boolean", "description": "A failing test reproduced the reported behaviour"},
        "root_cause": {"type": "string"},
        "fix_summary": {"type": "string"},
        "test_added": {"type": "string", "description": "Path and name of the regression test"},
        "pr_url": {"type": ["string", "null"]},
    },
    "required": ["reproduced", "root_cause", "fix_summary", "test_added", "pr_url"],
}


def parse_repo_map(spec: str) -> dict[str, str]:
    """'Fake CRM=Tooom123/hcs-sandbox-fake-crm; Odoo CRM=org/repo' -> {'fake crm': 'Tooom123/...', ...}"""
    out: dict[str, str] = {}
    for part in spec.replace("\n", ";").split(";"):
        if "=" in part:
            name, repo = part.split("=", 1)
            if name.strip() and repo.strip():
                out[name.strip().lower()] = repo.strip()
    return out


def branch_for(case_id: str) -> str:
    return f"feature/hcs-fix-{case_id}"


def build_prompt(case: StoredCase, repo: str) -> str:
    e = build_escalation(case)
    user, obs, agent = e["user_declared"], e["observed"], e["agent_declared"]
    checks = "\n".join(f"- `{k}`: {'ok' if v else 'FAILED'}" for k, v in (obs["checks"] or {}).items()) or "-"
    steps = "\n".join(f"{i}. {s['summary']}" for i, s in enumerate(e["attempted_steps"], 1)) or "-"
    ctx = e["context"]
    return f"""You are fixing a defect in the GitHub repository https://github.com/{repo}, reported by H Companion
(a computer-use support assistant) from an assisted user session. Case `{case.case_id}`.
This repository is a sandbox used for testing; treat it like a real codebase.

## Context
- Software: {ctx['software']} {ctx['software_version'] or ''} on {ctx['os']}
- User role: {user['role'] or '-'}
- Goal: {user['goal'] or '-'}
- Symptom reported by the user: {user['symptom'] or '-'}

## What was observed (verified by a separate read-only check, not the agent's claim)
- Expected (postcondition): {obs['postcondition'] or '-'}
- Observed: {obs['observed_state'] or '-'}
{checks}

## What the assistant did
{steps}

Agent summary: {agent['summary'] or '-'}
Blocked on: {e['blocked_on'] or '-'}
Suspected cause (hypothesis from support, may be wrong): {e['suspected_cause'] or '-'}

## Your task
1. Reproduce first: add an automated test that fails because of the behaviour observed above.
2. Find the root cause and fix it with the smallest reasonable change. Do not modify unrelated files and do not
   weaken or delete existing tests.
3. Run the whole test suite; everything must pass.
4. Push a branch named `{branch_for(case.case_id)}` and open a pull request against the default branch, titled
   "fix: <short description> (H Companion case {case.case_id})". In the PR body: root cause, fix, the test you
   added, and "Reported by H Companion, case {case.case_id}".
5. If you cannot reproduce the defect, do not open a pull request; explain why in the structured output.
Finish by providing the structured output (reproduced, root_cause, fix_summary, test_added, pr_url).
"""


# ----------------------------------------------------------------------------------------------- providers
class Provider(Protocol):
    name: str
    simulated: bool

    def create(self, *, prompt: str, repo: str, title: str, tags: list[str]) -> dict[str, Any]: ...
    def get(self, session_id: str) -> dict[str, Any]: ...
    def messages(self, session_id: str) -> list[dict[str, Any]]: ...
    def send(self, session_id: str, message: str) -> None: ...


class DevinError(RuntimeError):
    pass


@dataclass
class DevinProvider:
    api_key: str
    org_id: str
    base_url: str = "https://api.devin.ai"
    max_acu: int | None = 5
    timeout_s: float = 20.0
    name: str = "devin"
    simulated: bool = False

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/v3/organizations/{self.org_id}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise DevinError(f"Devin API {method} {path}: {e.code} {e.read().decode(errors='replace')[:300]}") from e
        except (urllib.error.URLError, OSError) as e:
            raise DevinError(f"Devin API unreachable: {e}") from e

    def create(self, *, prompt: str, repo: str, title: str, tags: list[str]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "prompt": prompt, "title": title, "repos": [repo], "tags": tags,
            "structured_output_schema": RESULT_SCHEMA,
        }
        if self.max_acu:
            body["max_acu_limit"] = self.max_acu
        return self._call("POST", "/sessions", body)

    def get(self, session_id: str) -> dict[str, Any]:
        return self._call("GET", f"/sessions/{session_id}")

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        d = self._call("GET", f"/sessions/{session_id}/messages")
        return d.get("items", []) if isinstance(d, dict) else list(d or [])

    def send(self, session_id: str, message: str) -> None:
        self._call("POST", f"/sessions/{session_id}/messages", {"message": message})


@dataclass
class MockProvider:
    """Simulated Devin: running for `run_s` seconds, then exits with a (simulated) pull request."""

    run_s: float = 6.0
    name: str = "mock"
    simulated: bool = True
    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create(self, *, prompt: str, repo: str, title: str, tags: list[str]) -> dict[str, Any]:
        sid = f"devin-mock-{uuid.uuid4().hex[:10]}"
        self._sessions[sid] = {"repo": repo, "t0": time.time(), "case": next((t[5:] for t in tags if t.startswith("case:")), "")}
        return {"session_id": sid, "url": f"https://app.devin.ai/sessions/{sid} (simulated)", "status": "new",
                "pull_requests": []}

    def get(self, session_id: str) -> dict[str, Any]:
        s = self._sessions.get(session_id)
        if s is None:
            raise DevinError(f"unknown simulated session {session_id}")
        if time.time() - s["t0"] < self.run_s:
            return {"session_id": session_id, "status": "running", "status_detail": "working", "pull_requests": []}
        pr = f"https://github.com/{s['repo']}/pull/0 (simulated)"
        return {
            "session_id": session_id, "status": "exit", "pull_requests": [{"pr_url": pr, "pr_state": "open"}],
            "structured_output": {"reproduced": True, "root_cause": "(simulated)", "fix_summary": "(simulated)",
                                  "test_added": "(simulated)", "pr_url": pr},
        }

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        return self._sessions.get(session_id, {}).get("messages", [])

    def send(self, session_id: str, message: str) -> None:
        self._sessions.setdefault(session_id, {}).setdefault("messages", []).append({"source": "user", "message": message})


def make_provider(settings) -> Provider:
    if settings.fix_provider == "devin" or (settings.fix_provider == "auto" and settings.devin_api_key):
        if not (settings.devin_api_key and settings.devin_org_id):
            raise DevinError("Devin provider needs DEVIN_API_KEY and DEVIN_ORG_ID")
        return DevinProvider(settings.devin_api_key, settings.devin_org_id, settings.devin_api_base,
                             settings.fix_max_acu or None)
    return MockProvider(run_s=settings.fix_mock_run_s)


# ----------------------------------------------------------------------------------------------- service
class AutoFixer:
    def __init__(self, settings, store, provider: Provider | None = None, announcer: Announcer | None = None):
        self.settings = settings
        self.store = store
        self.announcer = announcer  # Zak's voice: each step of the Devin debug, said aloud
        self.repos = parse_repo_map(settings.fix_repos)
        self._provider = provider
        self._provider_error: str | None = None

    @property
    def provider(self) -> Provider | None:
        if self._provider is None and self._provider_error is None:
            try:
                self._provider = make_provider(self.settings)
            except DevinError as e:
                self._provider_error = str(e)
        return self._provider

    def repo_for(self, case: StoredCase) -> str | None:
        return self.repos.get(str(case.report.get("software", "")).strip().lower())

    def auto_eligible(self, case: StoredCase) -> bool:
        return (self.settings.fix_auto and case.report.get("category") == "suspected_product_defect"
                and self.repo_for(case) is not None)

    def request(self, case: StoredCase, *, trigger: str) -> dict[str, Any]:
        """Start a fix session for this case (idempotent: one per case)."""
        existing = self.store.get_fix(case.case_id)
        if existing:
            return existing
        repo = self.repo_for(case)
        if repo is None:
            raise ValueError(f"software {case.report.get('software')!r} is not on the fix allowlist (HCS_FIX_REPOS)")
        provider = self.provider
        if provider is None:
            raise DevinError(self._provider_error or "no fix provider")
        title = f"H Companion case {case.case_id}: {str(case.report.get('symptom') or case.report.get('goal'))[:80]}"
        tags = ["h-companion", f"case:{case.case_id}", "sandbox" if "sandbox" in repo else "vendor"]
        fix = {"case_id": case.case_id, "provider": provider.name, "simulated": provider.simulated, "repo": repo,
               "software": case.report.get("software"),
               "branch": branch_for(case.case_id), "trigger": trigger, "status": "requested"}
        try:
            s = provider.create(prompt=build_prompt(case, repo), repo=repo, title=title, tags=tags)
            fix.update(session_id=s.get("session_id"), session_url=s.get("url"), status=s.get("status", "new"))
        except DevinError as e:
            fix.update(status="error", error=str(e))
        self.store.save_fix(fix)
        self._announce(None, fix)
        return self.store.get_fix(case.case_id)

    def _announce(self, old: dict[str, Any] | None, new: dict[str, Any]) -> None:
        if self.announcer is not None:
            self.announcer.say(*fix_lines(old, new))

    def refresh(self, case_id: str) -> dict[str, Any] | None:
        fix = self.store.get_fix(case_id)
        if not fix or not fix.get("session_id") or fix["status"] in TERMINAL or self.provider is None:
            return fix
        try:
            s = self.provider.get(fix["session_id"])
        except DevinError as e:
            fix["last_error"] = str(e)
            self.store.save_fix(fix)
            return fix
        old = dict(fix)
        prs = s.get("pull_requests") or []
        fix.update(status=s.get("status", fix["status"]), status_detail=s.get("status_detail"),
                   pr_url=prs[0]["pr_url"] if prs else fix.get("pr_url"),
                   pr_state=prs[0].get("pr_state") if prs else fix.get("pr_state"),
                   result=s.get("structured_output") or fix.get("result"),
                   acus=s.get("acus_consumed", fix.get("acus")))
        # Devin waits for us (missing access, a question...): bring its last message to the dashboard
        if fix.get("status_detail") == "waiting_for_user":
            try:
                said = [m for m in self.provider.messages(fix["session_id"]) if m.get("source") == "devin"]
                fix["devin_says"] = said[-1].get("message") if said else fix.get("devin_says")
            except DevinError:
                pass
        else:
            fix.pop("devin_says", None)
        self.store.save_fix(fix)
        self._announce(old, fix)
        return fix

    def reply(self, case_id: str, message: str) -> dict[str, Any]:
        """Answer Devin from the support dashboard (e.g. after granting repo access)."""
        fix = self.store.get_fix(case_id)
        if not fix or not fix.get("session_id"):
            raise ValueError("no Devin session for this case")
        if self.provider is None:
            raise DevinError(self._provider_error or "no fix provider")
        self.provider.send(fix["session_id"], message)
        fix.setdefault("replies", []).append(message)
        fix.pop("devin_says", None)
        self.store.save_fix(fix)
        return fix

    def poll_open(self) -> int:
        n = 0
        for fix in self.store.list_fixes():
            if fix.get("session_id") and not is_done(fix):
                self.refresh(fix["case_id"])
                n += 1
        return n
