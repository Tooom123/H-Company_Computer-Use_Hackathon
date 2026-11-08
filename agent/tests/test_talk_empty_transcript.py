"""Silence must not kill the desktop voice runtime or consume a feedback dictation."""

import argparse
from types import SimpleNamespace

import pytest

from hcs_agent import a11y, cli, voice
from hcs_agent.contract import State
from hcs_agent.desktop_feedback import DesktopFeedback


@pytest.fixture
def talk(monkeypatch, tmp_path):
    state = SimpleNamespace(texts=[], requests=[], flashes=[], controls=0, starts=0, stops=0)

    class PTT:
        key_name = "ctrl+shift+h"

        def __init__(self, **kwargs):
            self.transcripts = SimpleNamespace(empty=lambda: True)

        def start(self):
            state.starts += 1

        def stop(self):
            state.stops += 1

        def wait_transcript(self, **kwargs):
            if state.texts:
                return state.texts.pop(0)
            # The operator, not an empty transcript, ends this otherwise ongoing listener.
            raise KeyboardInterrupt

    def start_control(*args):
        state.controls += 1

    monkeypatch.setattr(voice, "PushToTalk", PTT)
    monkeypatch.setattr(voice, "IntentRouter", lambda _: pytest.fail("Sponsor coaching must stay local"))
    monkeypatch.setattr(cli, "ProcedureRegistry", lambda: SimpleNamespace(get=lambda _: None))
    monkeypatch.setattr(cli, "make_backend", lambda _: SimpleNamespace())
    monkeypatch.setattr(cli, "_start_control", start_control)
    monkeypatch.setattr(cli, "_execute", lambda req, *a, **kw: state.requests.append(req) or 0)
    monkeypatch.setattr(cli, "_flash", lambda ov, text, *a, **kw: state.flashes.append(text))
    monkeypatch.setattr(cli, "_VOICE", {"ptt": None, "state": None, "last_text": None})
    monkeypatch.setitem(cli._MAGNET, "current", None)
    monkeypatch.setitem(cli._MAGNET, "widget", None)
    monkeypatch.setitem(cli._SPEECH, "speaker", None)
    state.feedback = DesktopFeedback()
    monkeypatch.setattr(cli, "_FEEDBACK", state.feedback)
    state.args = argparse.Namespace(software="cognition", no_overlay=True, mock=True,
                                   runs_dir=str(tmp_path), key="ctrl+shift+h", confirm=False, once=False)
    state.directory = tmp_path
    return state


@pytest.mark.parametrize("software", ["cognition", "hcompany"])
@pytest.mark.parametrize("text", ["", " \t\n ", "\u2003\u00a0"])
def test_empty_final_retries_without_task_labels_or_runtime_restart(talk, software, text):
    talk.args.software = software
    talk.texts = [text]
    assert cli.cmd_talk(talk.args) == 0
    assert talk.controls == talk.starts == talk.stops == 1
    assert talk.requests == []
    assert cli._VOICE["last_text"] is None
    assert list(talk.directory.iterdir()) == []
    assert talk.flashes == ["I didn't catch a question. Hold the talk key, speak, then release to try again."]


def test_valid_question_after_silence_uses_the_same_live_listener(talk):
    question = "Montre-moi le menu Ask sans lancer de tâche."
    talk.texts = ["", " \t ", question]
    assert cli.cmd_talk(talk.args) == 0
    assert talk.controls == talk.starts == talk.stops == 1
    assert [req.goal for req in talk.requests] == [question]
    assert cli._VOICE["last_text"] == question
    assert len(talk.flashes) == 2


def test_silence_preserves_armed_feedback_for_the_next_actual_comment(talk):
    directory = talk.directory / "sess_finished"
    directory.mkdir()
    it = SimpleNamespace(request=SimpleNamespace(session_id="sess_finished"), state=State.resolved,
                         report=SimpleNamespace(), runs_dir=directory)
    talk.feedback.register(it)
    talk.feedback.arm({"session_id": "sess_finished"})
    talk.texts = [" \n"]
    assert cli.cmd_talk(talk.args) == 0
    assert talk.feedback.status()["dictation_armed"] is True
    assert list(directory.iterdir()) == []
    assert talk.requests == []


@pytest.mark.parametrize("count", [0, 8])
def test_native_startup_reports_native_scope_without_browser_fallback(talk, monkeypatch, capsys, count):
    talk.args.mock = False
    monkeypatch.setenv("HCS_AX_NATIVE_BUNDLE_ID", "com.exafunction.windsurf")
    monkeypatch.setattr(a11y, "available", lambda: True)
    monkeypatch.setattr(a11y, "warm_up", lambda: count)
    monkeypatch.setattr(a11y, "page", lambda: None)
    assert cli.cmd_talk(talk.args) == 0
    output = capsys.readouterr().out
    assert "native accessibility tree:" in output
    assert "browser accessibility tree:" not in output
    assert "Holo will be used until one is open" not in output
    if count:
        assert "8 controls in the focused native window" in output
    else:
        assert "no browser or screenshot fallback" in output
