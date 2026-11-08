"""Channel recovery and actual bridge-dispatch tests, with no desktop or H calls."""
from types import SimpleNamespace

import httpx
import pytest

import pilot.desktop_backend as module
from hcs_agent.backend import HBackend


@pytest.fixture
def chrome_bridge(monkeypatch):
    """No real NSWorkspace lookup, desktop capture or input in these tests."""
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    return module.RestrictedDesktopBridge(
        api_key='offline-test-key', frontmost_bundle_id=lambda: 'com.google.Chrome')


@pytest.fixture
def channel(monkeypatch):
    calls = {'stopped': [], 'opened': 0, 'requests': []}
    state = {'status': 'running', 'http_status': 200, 'serving': True, 'network_error': False,
             'bundle': 'com.google.Chrome'}
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    wrapper = SimpleNamespace(_api_key='offline-test-key', get_base_url=lambda: 'https://h.invalid')

    def init(self, **kwargs):
        self._client = SimpleNamespace(_client_wrapper=wrapper)
        self._desktop_session_id = 'old-channel'
        self.screenshot_max_width = 1280

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
    monkeypatch.setattr(module.PilotHBackend, '_open_desktop_channel', open_channel)
    monkeypatch.setattr(module, 'serving_bridges', lambda ids: ids if state['serving'] else [])
    monkeypatch.setattr(module, 'stop_bridges', lambda ids: calls['stopped'].append(ids))
    return module.PilotHBackend(frontmost_bundle_id=lambda: state['bundle']), state, calls


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
    monkeypatch.setattr(module.PilotHBackend, '_open_desktop_channel', failed_setup)
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


@pytest.mark.parametrize('name', [
    'run_command', 'run_command_desktop', 'read_file', 'write_file',
    'drag_and_drop', 'mouse_press', 'mouse_release', 'close', 'future_shell_method',
    'press_key', 'release_key',
])
def test_restricted_dispatch_rejects_before_any_driver_access(name):
    class UntouchableDriver:
        def __getattribute__(self, attr):
            pytest.fail(f'Denied command reached driver attribute {attr}')

    bridge = module.RestrictedDesktopBridge(api_key='offline-test-key')
    bridge._driver = UntouchableDriver()
    result, error = bridge._dispatch(name, {})
    assert result is None
    assert error == f"command {name!r} is not supported by this desktop bridge"


@pytest.mark.parametrize('name,args', [
    ('click', {'x': 12, 'y': 34, 'button': 'left'}),
    ('double_click', {'x': 12, 'y': 34}),
    ('mouse_move_to', {'x': 12, 'y': 34}),
    ('write', {'text': 'DEMO-ACHAT-029'}),
    ('write_at', {'x': 12, 'y': 34, 'text': 'DEMO-ACHAT-029', 'press_enter': True}),
    ('hotkey', {'keys': ['command', 'a']}),
    ('tap_key', {'key': 'enter'}),
    ('scroll_by_n_clicks', {'direction': 'down', 'clicks': 2}),
    ('scroll_by_n_pxs', {'direction': 'down', 'pixels': 120}),
    ('scroll_at', {'x': 12, 'y': 34, 'direction': 'down', 'clicks': 2}),
])
def test_restricted_dispatch_preserves_normal_input(chrome_bridge, name, args):
    calls = []

    class FakeDriver:
        def __getattr__(self, method):
            def record(**kwargs):
                calls.append((method, kwargs))
            return record

    bridge = chrome_bridge
    bridge._driver = FakeDriver()
    assert bridge._dispatch(name, args) == (None, None)
    assert calls == [(name, args)]


@pytest.mark.parametrize('name,value,expected', [
    ('platform', 'darwin', 'darwin'),
    ('screenshot_b64', 'offline-image', 'offline-image'),
    ('get_screen_size', (1280, 832), [1280, 832]),
    ('get_mouse_position', (12, 34), [12, 34]),
    ('get_accessibility_tree', '<empty/>', '<empty/>'),
    ('get_number_of_pixels_scrolled_per_click', 40, 40),
])
def test_restricted_dispatch_preserves_observation(chrome_bridge, name, value, expected):
    bridge = chrome_bridge
    attribute = value if name == 'platform' else lambda: value
    bridge._driver = SimpleNamespace(**{name: attribute})
    assert bridge._dispatch(name, {}) == (expected, None)


def test_restricted_dispatch_serializes_bundled_observation(chrome_bridge):
    from hai_drivers.desktop.interface import ObservationSnapshot

    snapshot = ObservationSnapshot(screenshot_b64='offline-image', cursor_position=(12, 34))
    bridge = chrome_bridge
    bridge._driver = SimpleNamespace(get_observation_snapshot=lambda: snapshot)
    assert bridge._dispatch('get_observation_snapshot', {}) == (snapshot.model_dump(mode='json'), None)


def test_open_channel_installs_restricted_bridge_without_permissive_fallback(monkeypatch):
    calls = []
    wrapper = SimpleNamespace(_api_key='offline-test-key', get_base_url=lambda: 'https://h.invalid')

    def init(self, **kwargs):
        self._client = SimpleNamespace(_client_wrapper=wrapper)
        self._desktop_session_id = None
        self.screenshot_max_width = 1280

    def forbidden(self):
        pytest.fail('The permissive HBackend desktop bridge must never be opened')

    monkeypatch.setattr(HBackend, '__init__', init)
    monkeypatch.setattr(HBackend, '_desktop_channel', forbidden)
    monkeypatch.setattr(module.RestrictedDesktopBridge, 'preflight', lambda self: calls.append(('preflight', self)))
    monkeypatch.setattr(module, 'ensure_bridges', lambda bridges: calls.append(('ensure', bridges[0])))
    backend = module.PilotHBackend()
    sid = backend._desktop_channel()
    assert [kind for kind, _ in calls] == ['preflight', 'ensure']
    bridge = calls[0][1]
    assert calls[1][1] is bridge
    assert isinstance(bridge, module.RestrictedDesktopBridge)
    assert bridge.max_width == 1280
    assert sid == bridge.session_id == backend._desktop_session_id
    assert backend.adapter_revision == 'pilot-bridge-health-v4'


@pytest.mark.parametrize('name', sorted(module.RestrictedDesktopBridge.commands))
@pytest.mark.parametrize('bundle', [None, '', 'com.openai.codex', 'com.google.Chrome.helper'])
def test_foreground_guard_blocks_every_command_before_driver_access(chrome_bridge, name, bundle):
    class UntouchableDriver:
        def __getattribute__(self, attr):
            pytest.fail(f'Blocked foreground reached driver attribute {attr}')

    chrome_bridge._driver = UntouchableDriver()
    chrome_bridge._frontmost_bundle_id = lambda: bundle
    assert chrome_bridge._dispatch(name, {}) == (None, module.RestrictedDesktopBridge.foreground_error)


@pytest.mark.parametrize('name', ['screenshot_b64', 'get_accessibility_tree', 'get_observation_snapshot', 'click'])
@pytest.mark.parametrize('error', [ImportError, RuntimeError, AttributeError])
def test_foreground_lookup_failure_is_closed_and_does_not_leak(chrome_bridge, name, error):
    def unavailable():
        raise error('private-app-name /private/secret/path')

    chrome_bridge._frontmost_bundle_id = unavailable
    # The driver is not even initialized; any access would fail the test.
    result, message = chrome_bridge._dispatch(name, {})
    assert result is None
    assert message == module.RestrictedDesktopBridge.foreground_error
    assert 'secret' not in message and 'private-app' not in message


@pytest.mark.parametrize('platform', ['linux', 'win32', 'unknown'])
def test_foreground_guard_rejects_non_macos_even_with_chrome_reader(chrome_bridge, monkeypatch, platform):
    monkeypatch.setattr(module.sys, 'platform', platform)

    def must_not_read():
        pytest.fail('Non-macOS must be rejected before native lookup')

    chrome_bridge._frontmost_bundle_id = must_not_read
    for name in chrome_bridge.commands:
        assert chrome_bridge._dispatch(name, {}) == (None, chrome_bridge.foreground_error)


def test_foreground_is_rechecked_for_each_dispatch(chrome_bridge):
    bundles = iter(['com.google.Chrome', 'com.openai.codex', 'com.google.Chrome'])
    calls = []
    chrome_bridge._frontmost_bundle_id = lambda: next(bundles)
    chrome_bridge._driver = SimpleNamespace(screenshot_b64=lambda: calls.append('capture') or 'image')
    assert chrome_bridge._dispatch('screenshot_b64', {}) == ('image', None)
    assert chrome_bridge._dispatch('screenshot_b64', {}) == (None, chrome_bridge.foreground_error)
    assert chrome_bridge._dispatch('screenshot_b64', {}) == ('image', None)
    assert calls == ['capture', 'capture']


def test_forbidden_command_does_not_call_foreground_reader(chrome_bridge):
    def must_not_read():
        pytest.fail('Allowlist rejection must precede native lookup')

    chrome_bridge._frontmost_bundle_id = must_not_read
    assert chrome_bridge._dispatch('run_command', {'command': 'not-executed'}) == (
        None, "command 'run_command' is not supported by this desktop bridge")


@pytest.mark.parametrize('bundle', ['com.google.Chrome', 'com.openai.codex', None])
def test_native_reader_uses_frontmost_bundle_without_activation(monkeypatch, bundle):
    calls = []
    app = SimpleNamespace(bundleIdentifier=lambda: calls.append('bundle') or bundle)
    workspace = SimpleNamespace(frontmostApplication=lambda: calls.append('frontmost') or app)
    fake_appkit = SimpleNamespace(NSWorkspace=SimpleNamespace(
        sharedWorkspace=lambda: calls.append('workspace') or workspace))
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    monkeypatch.setitem(module.sys.modules, 'AppKit', fake_appkit)
    assert module._macos_frontmost_bundle_id() == bundle
    assert calls == ['workspace', 'frontmost', 'bundle']


def test_native_reader_handles_missing_frontmost_application(monkeypatch):
    workspace = SimpleNamespace(frontmostApplication=lambda: None)
    fake_appkit = SimpleNamespace(NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: workspace))
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    monkeypatch.setitem(module.sys.modules, 'AppKit', fake_appkit)
    assert module._macos_frontmost_bundle_id() is None


def test_native_reader_does_not_import_appkit_off_macos(monkeypatch):
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    monkeypatch.setitem(module.sys.modules, 'AppKit', None)
    assert module._macos_frontmost_bundle_id() is None


@pytest.mark.parametrize('method', ['run_attempt', 'run_guidance', 'verify'])
@pytest.mark.parametrize('bundle', [None, '', 'com.openai.codex', 'com.google.Chrome.helper'])
def test_backend_blocks_before_parent_or_network(channel, monkeypatch, method, bundle):
    backend, state, calls = channel
    state['bundle'] = bundle

    class UntouchableClient:
        def __getattribute__(self, attr):
            pytest.fail(f'Off-scope launch accessed client {attr}')

    def forbidden(*args, **kwargs):
        pytest.fail('Off-scope launch reached parent backend')

    backend._client = UntouchableClient()
    monkeypatch.setattr(HBackend, method, forbidden)
    result = getattr(backend, method)()
    assert result.status == 'failed' and result.h_session_id is None
    assert result.error == module.RestrictedDesktopBridge.foreground_error
    if method != 'verify':
        assert result.declared.outcome == 'blocked'
        assert result.declared.blocker_category.value == 'environment'
    assert calls['opened'] == 0 and calls['requests'] == [] and calls['stopped'] == []


@pytest.mark.parametrize('method', ['run_attempt', 'run_guidance', 'verify'])
def test_backend_allows_parent_entry_only_when_chrome_active(channel, monkeypatch, method):
    backend, _, _ = channel
    calls = []
    sentinel = object()
    def parent(self, *args, **kwargs):
        calls.append((args, kwargs))
        return sentinel
    monkeypatch.setattr(HBackend, method, parent)
    assert getattr(backend, method)('offline-argument', example=True) is sentinel
    assert calls == [(('offline-argument',), {'example': True})]


@pytest.mark.parametrize('tag', ['before', 'after'])
def test_local_evidence_is_not_captured_off_scope(channel, monkeypatch, tmp_path, tag):
    backend, state, _ = channel
    state['bundle'] = 'com.openai.codex'
    def forbidden(*args, **kwargs):
        pytest.fail('Off-scope evidence reached parent screenshot')
    monkeypatch.setattr(HBackend, 'screenshot', forbidden)
    path = tmp_path / f'{tag}.png'
    assert backend.screenshot(path) is None
    assert not path.exists()


def test_local_evidence_forwards_when_chrome_active(channel, monkeypatch, tmp_path):
    backend, _, _ = channel
    calls = []
    path = tmp_path / 'before.png'
    monkeypatch.setattr(HBackend, 'screenshot', lambda self, target: calls.append(target) or target)
    assert backend.screenshot(path) == path
    assert calls == [path]
    assert not path.exists()  # The fake parent performed no capture or write.


@pytest.mark.parametrize('failure', ['lookup_exception', 'non_macos'])
def test_shared_guard_blocks_backend_and_evidence_on_uncertainty(channel, monkeypatch, tmp_path, failure):
    backend, _, calls = channel
    def forbidden(*args, **kwargs):
        pytest.fail('Uncertain foreground reached parent backend')
    def broken_lookup():
        raise RuntimeError('/private/secret/path')
    if failure == 'non_macos':
        monkeypatch.setattr(module.sys, 'platform', 'linux')
    else:
        backend._frontmost_bundle_id = broken_lookup
    for method in ['run_attempt', 'run_guidance', 'verify']:
        monkeypatch.setattr(HBackend, method, forbidden)
        result = getattr(backend, method)()
        assert result.error == module.RestrictedDesktopBridge.foreground_error
    monkeypatch.setattr(HBackend, 'screenshot', forbidden)
    assert backend.screenshot(tmp_path / 'before.png') is None
    assert calls['requests'] == []


def test_backend_preparation_does_not_require_foreground():
    # Preparation happens while the companion panel is visible, before approval.
    assert module.PilotHBackend.preflight is HBackend.preflight


def test_off_scope_runner_escalates_without_images_or_h_session(channel, monkeypatch, tmp_path):
    from pathlib import Path
    from hcs_agent.contract import ApproveCommand, InterventionRequest
    from hcs_agent.knowledge import NoKnowledge
    from hcs_agent.procedures import ProcedureRegistry
    from hcs_agent.runner import Intervention

    backend, state, calls = channel
    state['bundle'] = 'com.openai.codex'
    backend.knowledge = NoKnowledge()
    monkeypatch.setattr(backend, 'preflight', lambda: None)
    def forbidden(*args, **kwargs):
        pytest.fail('Off-scope runner invoked parent capture or H session method')
    monkeypatch.setattr(HBackend, 'screenshot', forbidden)
    monkeypatch.setattr(HBackend, 'run_attempt', forbidden)
    monkeypatch.setattr(HBackend, 'verify', forbidden)
    request = InterventionRequest(software='odoo', role='commerçant', goal='Retrouver le fournisseur.',
        procedure_id='odoo_supplier_read_contact', mode='act')
    registry = ProcedureRegistry(Path(__file__).resolve().parents[2] / 'docs/scenarios')
    intervention = Intervention(request, backend, registry, lambda event: None, tmp_path)
    intervention.start()
    intervention.approve(ApproveCommand(approved=True))
    intervention.wait(2)
    assert intervention.state.value == 'escalated'
    assert intervention.report is not None
    assert intervention.report.declared.outcome == 'blocked'
    assert intervention.report.h_session_ids == []
    assert not any(item.kind == 'screenshot' for item in intervention.report.evidence)
    assert not list(tmp_path.rglob('*.png'))
    assert (tmp_path / request.session_id / 'report.json').is_file()
    assert calls['opened'] == 0 and calls['requests'] == [] and calls['stopped'] == []
