"""Zak: what is said at each step of a Devin fix, and that it never blocks or breaks the fix."""

from __future__ import annotations

import wave

from hcs_backend import announce
from hcs_backend.announce import Announcer, fix_lines
from hcs_backend.autofix import AutoFixer, MockProvider


def test_lines_on_transitions_only():
    req = {"software": "Fake CRM", "status": "new", "simulated": False}
    assert fix_lines(None, req) == ["Bug found in Fake CRM. I've asked Devin to fix it on a separate branch."]
    assert fix_lines(None, {**req, "simulated": True})[0].endswith("This one is simulated.")
    assert fix_lines(None, {**req, "status": "error"}) == [
        "I could not start Devin on Fake CRM. The case stays with support."]
    running = {**req, "status": "running", "status_detail": "working"}
    assert fix_lines(req, running) == []
    assert fix_lines(running, running) == []  # polling the same state says nothing
    ask = {**running, "status_detail": "waiting_for_user"}
    assert fix_lines(running, ask) == ["Devin needs you. Check the case in the support dashboard."]
    assert fix_lines(ask, ask) == []
    pr = {**ask, "pr_url": "https://github.com/o/r/pull/1"}
    assert fix_lines(ask, pr) == ["Devin opened a pull request on Fake CRM. It's ready for your review."]
    assert fix_lines(pr, {**pr, "status": "exit"}) == []  # finished with its PR: already announced
    assert fix_lines(running, {**running, "status": "error"}) == ["Devin stopped without a fix."]
    assert fix_lines(running, {**running, "status": "exit"}) == ["Devin finished, but no pull request was opened."]
    assert fix_lines(None, {"repo": "Tooom123/hcs-sandbox-fake-crm", "status": "new"})[0].startswith(
        "Bug found in hcs sandbox fake crm.")


def _announcer(tmp_path, fail=False):
    calls, played = [], []

    def synth(text):
        calls.append(text)
        if fail:
            raise RuntimeError("401")
        return b"\x00\x00" * 50

    def player(path):
        with wave.open(str(path)) as w:
            assert w.getframerate() == 22050
        played.append(path)

    return Announcer(synth, player, tmp_path / "zak"), calls, played


def test_speaks_in_order_and_caches(tmp_path):
    a, calls, played = _announcer(tmp_path)
    a.say("One", "Two", "  ", "One")
    assert a.wait_idle(5)
    assert a.spoken == ["One", "Two", "One"] and calls == ["One", "Two"] and len(played) == 3


def test_voice_failure_is_silent(tmp_path, capsys):
    a, _, played = _announcer(tmp_path, fail=True)
    a.say("One", "Two")
    assert a.wait_idle(5)
    assert not played and len(a.errors) == 2
    assert capsys.readouterr().out.count("Zak voice unavailable") == 1


def test_disabled_without_key_voice_or_when_muted(monkeypatch):
    for var in ("ELEVENLABS_API_KEY", "ELEVEN", "HCS_FIX_VOICE_ID", "ID_ZAK"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HCS_FIX_VOICE", "1")
    assert announce.make_announcer() is None
    monkeypatch.setenv("ELEVEN", "k")
    assert announce.make_announcer() is None  # no voice id
    monkeypatch.setenv("ID_ZAK", "v")
    monkeypatch.setattr(announce, "system_player", lambda: (lambda p: None))
    assert announce.make_announcer() is not None
    monkeypatch.setenv("HCS_FIX_VOICE", "0")
    assert announce.make_announcer() is None


class _Store:
    def __init__(self):
        self.fixes = {}

    def get_fix(self, cid):
        return dict(self.fixes[cid]) if cid in self.fixes else None

    def save_fix(self, fix):
        self.fixes[fix["case_id"]] = dict(fix)

    def list_fixes(self):
        return list(self.fixes.values())


class _Settings:
    fix_repos = "Fake CRM=Tooom123/hcs-sandbox-fake-crm"
    fix_auto = True


class _Case:
    case_id = "case_x"
    report = {"software": "Fake CRM", "category": "suspected_product_defect", "goal": "g", "symptom": "s",
              "procedure_id": "p", "status": "escalated", "escalation": {"blocked_on": "500 on save"}}


def test_full_simulated_fix_is_announced_once_per_step(tmp_path, monkeypatch):
    a, _, _ = _announcer(tmp_path)
    store = _Store()
    fixer = AutoFixer(_Settings(), store, provider=MockProvider(run_s=0.2), announcer=a)
    monkeypatch.setattr("hcs_backend.autofix.build_prompt", lambda case, repo: "prompt")
    fixer.request(_Case(), trigger="auto")
    fixer.refresh("case_x")
    import time

    time.sleep(0.3)
    fixer.refresh("case_x")
    fixer.refresh("case_x")
    assert a.wait_idle(5)
    assert a.spoken == ["Bug found in Fake CRM. I've asked Devin to fix it on a separate branch. This one is simulated.",
                        "Devin opened a pull request on Fake CRM. It's ready for your review."]
