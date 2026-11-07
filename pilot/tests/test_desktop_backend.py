"""Channel recovery tests: fake HTTP and bridges, no desktop or H calls."""
from types import SimpleNamespace

import httpx
import pytest

import pilot.desktop_backend as module
from hcs_agent.backend import HBackend


@pytest.fixture
def channel(monkeypatch):
    calls = {'stopped': [], 'opened': 0, 'requests': []}
    state = {'status': 'running', 'http_status': 200, 'serving': True, 'network_error': False}
    wrapper = SimpleNamespace(_api_key='offline-test-key', get_base_url=lambda: 'https://h.invalid')

    def init(self, **kwargs):
        self._client = SimpleNamespace(_client_wrapper=wrapper)
        self._desktop_session_id = 'old-channel'

    def open_channel(self):
        calls['opened'] += 1
        self._desktop_session_id = 'fresh-channel'
        return self._desktop_session_id

    def request(req):
        calls['requests'].append(req)
        if state['network_error']:
            raise httpx.ConnectError('offline', request=req)
        if state.get('invalid_json'):
            return httpx.Response(200, text='invalid JSON')
        return httpx.Response(state['http_status'], json={'status': state['status']})

    client = httpx.Client
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs: client(transport=httpx.MockTransport(request), **kwargs))
    monkeypatch.setattr(HBackend, '__init__', init)
    monkeypatch.setattr(HBackend, '_desktop_channel', open_channel)
    monkeypatch.setattr(module, 'serving_bridges', lambda ids: ids if state['serving'] else [])
    monkeypatch.setattr(module, 'stop_bridges', lambda ids: calls['stopped'].append(ids))
    return module.PilotHBackend(), state, calls


@pytest.mark.parametrize('status', ['pending', 'running', 'idle'])
def test_reuses_only_live_channel(channel, status):
    backend, state, calls = channel
    state['status'] = status
    assert backend._desktop_channel() == 'old-channel'
    assert calls['opened'] == 0 and calls['stopped'] == []
    assert str(calls['requests'][0].url) == 'https://h.invalid/api/v1/trajectories/old-channel'


@pytest.mark.parametrize('status', ['completed', 'failed', 'timed_out', 'interrupted'])
def test_terminal_channel_replaced_even_when_local_thread_alive(channel, status):
    backend, state, calls = channel
    state['status'] = status
    assert backend._desktop_channel() == 'fresh-channel'
    assert calls['stopped'] == [['old-channel']]
    assert calls['opened'] == 1


def test_missing_cloud_channel_replaced(channel):
    backend, state, calls = channel
    state['http_status'] = 404
    assert backend._desktop_channel() == 'fresh-channel'
    assert calls['stopped'] == [['old-channel']]


def test_dead_local_bridge_replaced(channel):
    backend, state, calls = channel
    state['serving'] = False
    assert backend._desktop_channel() == 'fresh-channel'
    assert calls['stopped'] == [['old-channel']]


@pytest.mark.parametrize('change', [
    {'http_status': 401}, {'http_status': 403}, {'http_status': 500},
    {'http_status': 302}, {'status': 'unexpected'}, {'status': None}, {'status': {}},
    {'invalid_json': True}, {'network_error': True},
])
def test_uncertain_channel_fails_without_reuse_or_unrelated_cleanup(channel, change):
    backend, state, calls = channel
    state.update(change)
    with pytest.raises(module.DesktopConnectionError):
        backend._desktop_channel()
    assert calls['opened'] == 0 and calls['stopped'] == []


def test_initial_channel_created_without_lookup(channel):
    backend, _, calls = channel
    backend._desktop_session_id = None
    assert backend._desktop_channel() == 'fresh-channel'
    assert calls['requests'] == [] and calls['stopped'] == []


def test_setup_failure_is_typed(channel, monkeypatch):
    backend, _, _ = channel
    backend._desktop_session_id = None
    def failed_setup(self):
        raise TimeoutError('setup deadline')
    monkeypatch.setattr(HBackend, '_desktop_channel', failed_setup)
    with pytest.raises(module.DesktopConnectionError, match='ouvrir'):
        backend._desktop_channel()


def test_never_runs_team_wide_cleanup(channel, monkeypatch):
    backend, _, calls = channel
    def forbidden(self):
        pytest.fail('team-wide cleanup must never run')
    monkeypatch.setattr(HBackend, '_close_orphans', forbidden)
    backend._close_orphans()
    assert calls['requests'] == [] and calls['stopped'] == []


def test_failed_stop_does_not_open_second_bridge(channel, monkeypatch):
    backend, state, calls = channel
    state['status'] = 'failed'
    def failed_stop(ids):
        raise TimeoutError('still active')
    monkeypatch.setattr(module, 'stop_bridges', failed_stop)
    with pytest.raises(module.DesktopConnectionError):
        backend._desktop_channel()
    assert backend._desktop_session_id == 'old-channel' and calls['opened'] == 0


@pytest.mark.parametrize('method', ['run_attempt', 'run_guidance', 'verify'])
def test_connection_failure_becomes_failed_result_not_dead_runner(channel, monkeypatch, method):
    backend, _, _ = channel
    def fails(*args, **kwargs):
        raise module.DesktopConnectionError('Connexion indisponible')
    monkeypatch.setattr(HBackend, method, fails)
    result = getattr(backend, method)()
    assert result.status == 'failed' and result.error == 'Connexion indisponible'
    if method != 'verify':
        assert result.declared.outcome == 'blocked'
        assert result.declared.blocker_category.value == 'environment'


def test_unrelated_exception_not_converted(channel, monkeypatch):
    backend, _, _ = channel
    def bug(*args, **kwargs):
        raise ValueError('programming bug')
    monkeypatch.setattr(HBackend, 'run_attempt', bug)
    with pytest.raises(ValueError):
        backend.run_attempt()


def test_connection_error_finishes_intervention_with_report(channel, monkeypatch, tmp_path):
    from pathlib import Path
    from hcs_agent.contract import ApproveCommand, InterventionRequest
    from hcs_agent.knowledge import NoKnowledge
    from hcs_agent.procedures import ProcedureRegistry
    from hcs_agent.runner import Intervention

    backend, _, _ = channel
    backend.knowledge = NoKnowledge()
    monkeypatch.setattr(backend, 'preflight', lambda: None)
    monkeypatch.setattr(backend, 'screenshot', lambda path: None)
    def unavailable(*args, **kwargs):
        raise module.DesktopConnectionError('Connexion indisponible')
    monkeypatch.setattr(HBackend, 'run_attempt', unavailable)
    request = InterventionRequest(software='odoo', role='commerçant',
        goal='Retrouver le fournisseur.', procedure_id='odoo_supplier_read_contact', mode='act')
    registry = ProcedureRegistry(Path(__file__).resolve().parents[2] / 'docs/scenarios')
    intervention = Intervention(request, backend, registry, lambda event: None, tmp_path)
    intervention.start()
    intervention.approve(ApproveCommand(approved=True))
    intervention.wait(2)
    assert intervention.state.value == 'escalated'
    assert intervention.report is not None
    assert intervention.report.declared.outcome == 'blocked'
    assert intervention.report.verification.satisfied is not True
    assert (tmp_path / request.session_id / 'report.json').is_file()
