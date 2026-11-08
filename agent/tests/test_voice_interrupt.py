"""A new talk-key press wins before microphone startup or any transcript arrives."""
import queue
import threading
from types import SimpleNamespace

import pytest

from hcs_agent import cli
from hcs_agent.backend import MockBackend, AttemptResult
from hcs_agent.contract import ApproveCommand, CaseStatus, DeclaredResult, InterventionRequest, Mode, State
from hcs_agent.procedures import ProcedureRegistry
from hcs_agent.runner import Intervention


@pytest.fixture
def voice_state(monkeypatch):
    said, hushed = [], []
    monkeypatch.setattr(cli, '_VOICE', {'state': None, 'generation': 0, 'ptt': SimpleNamespace(transcripts=queue.Queue())})
    monkeypatch.setattr(cli, '_SPEECH', {'speaker': SimpleNamespace(stop=lambda: hushed.append(True),
                                                                  say=lambda *a, **kw: said.append(a))})
    monkeypatch.setattr(cli, '_MAGNET', {'current': None, 'level': 2, 'widget': None})
    return said, hushed


@pytest.mark.parametrize('state', [State.awaiting_user, State.running, State.verifying])
def test_beginning_dictation_interrupts_even_without_transcript_or_overlay(voice_state, state):
    stopped = []
    it = SimpleNamespace(state=state)
    def stop(command):
        stopped.append(command)
        it.state = State.stopping
    it.stop = stop
    cli._MAGNET['current'] = it
    cli._on_talk_voice_state('starting')
    assert len(stopped) == 1 and 'before transcription' in stopped[0].reason
    assert cli._VOICE['ptt'].transcripts.empty() and cli._new_request_pending()
    assert cli._VOICE['generation'] == 1
    cli._on_talk_voice_state('recording')
    cli._on_talk_voice_state('too_short')
    assert len(stopped) == 1 and it.state is State.stopping  # no automatic resume


@pytest.mark.parametrize('state', ['starting', 'recording', 'transcribing'])
def test_old_response_cannot_speak_over_new_dictation(voice_state, state):
    cli._VOICE['state'] = state
    cli._say('Old instruction')
    assert voice_state[0] == []


def test_request_superseded_during_routing_never_starts_a_task(voice_state, tmp_path):
    cli._VOICE.update(generation=2, state='too_short')
    request = InterventionRequest(software='h-company', procedure_id='generic', goal='Old request')
    assert cli._execute(request, MockBackend(), tmp_path, auto_approve=True,
                        overlay=False, voice_generation=1) == 3
    assert not list(tmp_path.iterdir()) and cli._MAGNET['current'] is None


def test_new_dictation_cancels_actor_and_saves_abandoned_trace(voice_state, tmp_path, monkeypatch):
    entered = threading.Event()
    backend = MockBackend(step_delay_s=0)
    def act(bound, task, attempt, on_step, stop_event, on_lookup):
        entered.set()
        assert stop_event.wait(3), 'Actor did not receive the stop gate'
        return AttemptResult('simulated-barge-in', 'interrupted', DeclaredResult(outcome='not_run'))
    monkeypatch.setattr(backend, 'run_attempt', act)
    monkeypatch.setattr(backend, 'verify', lambda *a: pytest.fail('No verification after the interruption'))
    request = InterventionRequest(software='h-company', procedure_id='generic', goal='Read public documentation',
                                  mode=Mode.act, autonomy=2)
    it = Intervention(request, backend, ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    cli._MAGNET['current'] = it
    it.start()
    it.approve(ApproveCommand())
    assert entered.wait(2)
    cli._on_talk_voice_state('starting')
    cli._on_talk_voice_state('error: microphone unavailable')
    it.wait(3)
    assert it.report.status is CaseStatus.abandoned and it._stop.is_set()
    assert (it.runs_dir / 'report.json').exists()
    assert cli._VOICE['ptt'].transcripts.empty()
