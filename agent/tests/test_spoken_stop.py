"""Exact spoken Stop is a local control, never a new task or an implied feedback label."""
import argparse
from types import SimpleNamespace

import pytest

from hcs_agent import cli, voice
from hcs_agent.contract import State


@pytest.mark.parametrize("text", ["stop", "Stop!", "STOP.", " stop task ", "Stop the task.",
                                 "arrête", "Arrête la tâche !", "arrete la tache", "ARRÊTE", "stop   task"])
def test_exact_stop_command(text):
    assert cli._is_stop_utterance(text)


@pytest.mark.parametrize("text", ["Where is the Stop button?", "Don't stop", "stop and open Odoo", "stopwatch", "non stop",
                                 "Explique comment arrêter la tâche", "Stop was confusing", "", "please stop"])
def test_mentions_and_longer_requests_are_not_local_stop_commands(text):
    assert not cli._is_stop_utterance(text)


def test_spoken_stop_calls_local_gate_without_any_label(monkeypatch):
    calls, silenced = [], []
    it = SimpleNamespace(state=State.running, stop=lambda cmd: calls.append(cmd))
    monkeypatch.setitem(cli._MAGNET, "current", it)
    monkeypatch.setattr(cli, "_hush", lambda: silenced.append(True))
    monkeypatch.setattr(cli, "_FEEDBACK", SimpleNamespace(consume_transcript=lambda _: False))
    assert cli._consume_talk_control("Arrête la tâche.")
    assert len(calls) == 1 and calls[0].reason == "Exact spoken Stop command"
    assert silenced == [True]
    it.state = State.stopping
    assert cli._consume_talk_control("Stop!")
    assert len(calls) == 1, "repeated stop preserves the original stop request"
    it.state = State.stopped
    assert cli._consume_talk_control("Stop")
    assert len(calls) == 1


def test_armed_feedback_has_priority_even_when_the_entire_comment_is_stop(monkeypatch):
    comments = []
    monkeypatch.setattr(cli, "_FEEDBACK", SimpleNamespace(consume_transcript=lambda text: comments.append(text) or True))
    monkeypatch.setattr(cli, "_control_stop", lambda **_: pytest.fail("Feedback must not become a Stop command"))
    monkeypatch.setattr(cli, "_flash", lambda *a, **kw: None)
    assert cli._consume_talk_control("stop")
    assert comments == ["stop"]


def test_talk_routes_question_after_stop_but_never_stop_itself(tmp_path, monkeypatch):
    texts = iter(["Stop!", "Où se trouve le résultat de cette session ?"])
    class PTT:
        key_name = "ctrl+shift+h"
        def __init__(self, **kwargs):
            pass
        def start(self):
            pass
        def wait_transcript(self, **kwargs):
            return next(texts)
    monkeypatch.setattr(cli, "_VOICE", {"ptt": None, "state": None})
    monkeypatch.setattr(voice, "PushToTalk", PTT)
    monkeypatch.setattr(voice, "IntentRouter", lambda _: pytest.fail("Sponsor routing stays local"))
    monkeypatch.setattr(cli, "ProcedureRegistry", lambda: SimpleNamespace(get=lambda _: None))
    monkeypatch.setattr(cli, "make_backend", lambda _: SimpleNamespace())
    monkeypatch.setattr(cli, "_start_control", lambda *a: None)
    monkeypatch.setattr(cli, "_FEEDBACK", SimpleNamespace(consume_transcript=lambda _: False))
    monkeypatch.setitem(cli._MAGNET, "current", None)
    monkeypatch.setitem(cli._MAGNET, "widget", None)
    monkeypatch.setitem(cli._SPEECH, "speaker", None)
    requests, stops = [], []
    monkeypatch.setattr(cli, "_control_stop", lambda **kwargs: stops.append(kwargs) or False)
    monkeypatch.setattr(cli, "_execute", lambda request, *a, **kw: requests.append(request) or 0)
    args = argparse.Namespace(software="cognition", no_overlay=True, mock=True, runs_dir=str(tmp_path),
                              key="ctrl+shift+h", confirm=False, once=True)
    assert cli.cmd_talk(args) == 0
    assert len(stops) == 1
    assert len(requests) == 1 and requests[0].goal == "Où se trouve le résultat de cette session ?"
