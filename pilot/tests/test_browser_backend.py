"""Exercise the real bridge dispatcher using fakes; no H/desktop/browser calls."""
from types import SimpleNamespace
import threading

import httpx
import pytest

import pilot.browser_backend as module
from pilot.browser_runtime import BrowserConfig, BrowserCredentials, BrowserRuntimeError


class FakeRuntime:
    config = BrowserConfig()
    debugging_port = 37901
    target_id = 'owned-target'

    def __init__(self):
        self.started = 0
        self.closed = 0
        self.safe = True
        self.owned = True

    def start(self):
        self.started += 1
        self.assert_safe()

    def assert_safe(self):
        if not self.safe:
            raise BrowserRuntimeError('Blocked test runtime.')

    def assert_owned_endpoint(self):
        self.assert_safe()
        if not self.owned:
            raise BrowserRuntimeError('Wrong endpoint.')

    def screenshot(self):
        self.assert_safe()
        return b'only-viewport'

    def close(self):
        self.closed += 1

    def reset_page(self):
        self.reset = True


class FakeDriver:
    def __init__(self):
        self.calls = []
        self.tabs = ['owned-target']
        self.url = BrowserConfig().start_url
        self.after = lambda: None

    def get_tabs(self):
        return self.tabs

    def get_active_tab(self):
        return self.tabs[0]

    def current_url(self):
        return self.url

    def __getattr__(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            self.after()
            return None
        return call


@pytest.fixture
def bridge():
    bridge = module.RestrictedBrowserBridge(runtime=FakeRuntime(), api_key='offline-test')
    bridge._driver = FakeDriver()
    return bridge


@pytest.mark.parametrize('name', ['execute_script', 'get_cookies', 'add_cookies', 'delete_cookies',
    'get_local_storage', 'set_local_storage', 'get_logs', 'get_html', 'get_viewport_html', 'viewport_markdown',
    'read_file', 'write_file', 'upload_file', 'list_files', 'run_command', 'destroy',
    'new_tab', 'open_new_tab', 'switch_tab_by_id', 'close_active_tab', 'press_key', 'release_key',
    'enter_secret', 'fill_secret_at', 'future_unsafe_method'])
def test_forbidden_dispatch_never_accesses_driver(bridge, name):
    class Forbidden:
        def __getattribute__(self, name):
            pytest.fail('Forbidden method touched driver')
    bridge._driver = Forbidden()
    assert bridge._dispatch(name, {}) == (None, bridge.blocked_error)


@pytest.mark.parametrize('name,args', [
    ('click_at', {'x': 10, 'y': 20}), ('input_text', {'text': 'DEMO-ACHAT-029'}),
    ('write_at', {'x': 10, 'y': 20, 'text': 'supplier', 'enter': True}),
    ('scroll_at', {'x': 200, 'y': 200, 'dy': 100}),
    ('goto', {'url': BrowserConfig().origin + '/odoo/purchase'}),
    ('press_and_release_keys', {'keys': ['enter']}),
    ('hold_and_tap_keys', {'hold_keys': ['universal_command'], 'tap_keys': ['a']}),
])
def test_allowed_gestures_reach_driver(bridge, name, args):
    assert bridge._dispatch(name, args) == (None, None)
    assert bridge._driver.calls == [(name, args)]


@pytest.mark.parametrize('keys', [['ctrl', 'l'], ['command', 'o'], ['command', 'v'], ['ctrl', 'c'],
                                 ['alt', 'tab'], ['f12'], ['command', 'p'], ['ctrl', 'shift', 'i']])
def test_native_browser_and_clipboard_shortcuts_blocked(bridge, keys):
    assert bridge._dispatch('press_and_release_keys', {'keys': keys})[1] == bridge.blocked_error
    assert bridge._driver.calls == []


@pytest.mark.parametrize('url', ['file:///private/secret', 'https://example.com',
    BrowserConfig().origin + '/web/login', BrowserConfig().origin + '/web/database/manager',
    'javascript:alert(1)', BrowserConfig().origin + '/odoo?password=private'])
def test_navigation_outside_app_blocked_before_driver(bridge, url):
    assert bridge._dispatch('goto', {'url': url})[1] == bridge.blocked_error
    assert bridge._driver.calls == []


def test_redirect_result_is_discarded(bridge):
    bridge._driver.after = lambda: setattr(bridge._driver, 'url', 'https://example.com/private')
    assert bridge._dispatch('click_at', {'x': 1, 'y': 2}) == (None, bridge.blocked_error)
    assert len(bridge._driver.calls) == 1


def test_extra_tab_blocks_even_when_active_tab_is_safe(bridge):
    bridge._driver.tabs.append('unowned-target')
    assert bridge._dispatch('screenshot_b64', {}) == (None, bridge.blocked_error)
    assert bridge._driver.calls == []


def test_compound_observation_never_enables_dom_markdown(bridge):
    assert bridge._dispatch('observation_bundle', {'include_markdown': True}) == (None, None)
    assert bridge._driver.calls == [('observation_bundle', {'include_markdown': False})]


def test_stop_gate_precedes_all_driver_calls(bridge):
    bridge.stop_event.set()
    assert bridge._dispatch('click_at', {'x': 1, 'y': 2}) == (None, bridge.blocked_error)
    assert bridge._driver.calls == []


def test_errors_do_not_echo_driver_details_or_log_secrets(bridge, caplog):
    def fail():
        raise ValueError('PRIVATE-CREDENTIAL-SENTINEL')
    bridge._driver.after = fail
    result = bridge._dispatch('screenshot_b64', {})
    assert result == (None, bridge.blocked_error)
    assert 'PRIVATE-CREDENTIAL' not in caplog.text


def test_dead_endpoint_never_falls_back_to_visible_chrome(bridge, monkeypatch):
    bridge.runtime.owned = False
    monkeypatch.setattr(module.SeleniumBrowserBridge, '_ensure_local_chrome', lambda *a: pytest.fail('Visible fallback'))
    with pytest.raises(BrowserRuntimeError):
        bridge._ensure_local_chrome()


class FakeManager:
    def __init__(self):
        self.started = []
        self.stopped = []

    def ensure(self, bridges):
        self.started.extend(bridges)

    def serving(self, ids):
        return ids

    def stop(self, ids):
        self.stopped.append(ids)


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    def init(self, **kwargs):
        from hcs_agent.knowledge import NoKnowledge
        self.knowledge = NoKnowledge()
        self.model = 'holo4-35b-a3b'
        self._client = SimpleNamespace(_client_wrapper=SimpleNamespace(
            _api_key='offline', get_base_url=lambda: 'https://h.invalid'))
        self._close_orphans()
    monkeypatch.setattr(module.HBackend, '__init__', init)
    backend = module.BrowserHBackend(browser_config=BrowserConfig(),
        browser_credentials=BrowserCredentials('u', 'p', 'bu', 'bp'),
        browser_runtime=FakeRuntime(), bridge_manager=FakeManager())
    monkeypatch.setattr(backend, '_channel_status', lambda sid: 'running')
    # Most tests exercise orchestration, not transport; never reach H in tests.
    monkeypatch.setattr(backend, '_close_owned_channel', lambda sid: True)
    return backend


def test_actor_verifier_specs_share_one_owned_channel(backend):
    a = backend._agent_spec('actor', 'Act')
    v = backend._agent_spec('verifier', 'Verify')
    assert a['environments'] == v['environments']
    assert a['environments'][0]['kind'] == 'web'
    assert a['environments'][0]['host'] == 'user_device'
    assert a['environments'][0]['headless'] is True
    assert a['environments'][0]['start_url'] == BrowserConfig().start_url
    assert a['environments'][0]['mode']['width'] == 1280
    assert len(backend._manager.started) == 1
    assert 'screenshot_max_width' not in a['environments'][0]


def test_screenshot_is_viewport_and_does_not_call_desktop(backend, monkeypatch, tmp_path):
    monkeypatch.setattr(module.HBackend, 'screenshot', lambda *a: pytest.fail('Desktop capture'))
    path = tmp_path / 'frame.png'
    assert backend.screenshot(path) == path
    assert path.read_bytes() == b'only-viewport'
    backend.runtime.safe = False
    assert backend.screenshot(tmp_path / 'blocked.png') is None
    assert not (tmp_path / 'blocked.png').exists()


def test_close_stops_only_owned_channel_and_runtime(backend):
    sid = backend._browser_channel()
    backend.close()
    backend.close()
    assert backend._manager.stopped == [[sid]]
    assert backend.runtime.closed == 1
    with pytest.raises(BrowserRuntimeError):
        backend.preflight()


@pytest.mark.parametrize('state', ['pending', 'running', 'idle'])
def test_close_preserves_remote_channel_after_local_stop(backend, monkeypatch, state):
    sid = backend._browser_channel()
    requests = []
    real_client = module.httpx.Client
    def respond(request):
        assert backend._bridge.stop_event.is_set()
        assert backend._manager.stopped == [[sid]]
        assert request.url.path == f'/api/v1/trajectories/{sid}'
        requests.append(request.method)
        assert request.method == 'GET'
        return module.httpx.Response(200, json={'status': state})
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs:
        real_client(transport=module.httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(backend, '_close_owned_channel',
                        lambda owned: module.BrowserHBackend._close_owned_channel(backend, owned))
    backend.close()
    assert requests == ['GET']
    assert backend.runtime.closed == 1
    assert backend._lifecycle_observations[-1] == {'session_id': sid,
        'phase': 'remote_channel_preserved', 'status': state, 'remote_terminal_confirmed': False}
    with pytest.raises(BrowserRuntimeError):
        backend.preflight()


@pytest.mark.parametrize('state', ['interrupted', 'completed', 'missing'])
def test_already_ended_owned_channel_is_only_observed(backend, monkeypatch, state):
    sid = backend._browser_channel()
    backend._bridge.stop_event.set()
    real_client = module.httpx.Client
    def respond(request):
        assert request.method == 'GET'
        return module.httpx.Response(404 if state == 'missing' else 200, json={'status': state})
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs:
        real_client(transport=module.httpx.MockTransport(respond), **kwargs))
    assert module.BrowserHBackend._close_owned_channel(backend, sid)
    assert backend._lifecycle_observations[-1]['phase'] == 'remote_channel_terminal_observed'
    assert backend._lifecycle_observations[-1]['remote_terminal_confirmed'] is True


def test_cleanup_refuses_foreign_channel_or_open_dispatch_gate(backend, monkeypatch):
    sid = backend._browser_channel()
    monkeypatch.setattr(module.httpx, 'Client', lambda **kw: pytest.fail('Unexpected network call'))
    assert not module.BrowserHBackend._close_owned_channel(backend, 'foreign-id')
    backend._bridge.stop_event.clear()
    assert not module.BrowserHBackend._close_owned_channel(backend, sid)


def test_unconfirmed_channel_cleanup_still_closes_owned_browser(backend, monkeypatch):
    sid = backend._browser_channel()
    monkeypatch.setattr(backend, '_close_owned_channel', lambda owned: False)
    backend.close()
    assert backend._manager.stopped == [[sid]]
    assert backend.runtime.closed == 1


def test_cleanup_is_not_sent_if_local_bridge_failed_to_stop(backend, monkeypatch):
    backend._browser_channel()
    monkeypatch.setattr(backend._manager, 'stop', lambda ids: (_ for _ in ()).throw(TimeoutError()))
    monkeypatch.setattr(backend, '_close_owned_channel', lambda sid: pytest.fail('Live poller may recreate channel'))
    with pytest.raises(BrowserRuntimeError):
        backend.close()
    assert backend.runtime.closed == 1


def test_stale_bridge_is_not_replaced_when_remote_terminal_unconfirmed(backend, monkeypatch):
    backend._browser_channel()
    monkeypatch.setattr(backend, '_channel_status', lambda sid: 'completed')
    monkeypatch.setattr(backend, '_close_owned_channel', lambda sid: False)
    with pytest.raises(BrowserRuntimeError, match='did not confirm termination'):
        backend._browser_channel()
    assert backend._poisoned and len(backend._manager.started) == 1


def test_channel_observation_error_preserves_remote_and_closes_local(backend, monkeypatch):
    backend._browser_channel()
    real_client = module.httpx.Client
    def respond(request):
        assert request.method == 'GET'
        raise httpx.ConnectError('offline test', request=request)
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs:
        real_client(transport=module.httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(backend, '_close_owned_channel',
                        lambda owned: module.BrowserHBackend._close_owned_channel(backend, owned))
    backend.close()
    assert backend.runtime.closed == 1
    assert backend._lifecycle_observations[-1]['phase'] == 'remote_channel_preserved'
    assert backend._lifecycle_observations[-1]['status'] == 'unavailable'


def test_failed_channel_start_cannot_create_more_channels(backend, monkeypatch):
    starts = []
    def fail_start(bridges):
        starts.extend(bridges)
        raise TimeoutError('uncertain channel startup')
    monkeypatch.setattr(backend._manager, 'ensure', fail_start)
    with pytest.raises(BrowserRuntimeError):
        backend._browser_channel()
    assert backend._poisoned and backend._bridge.stop_event.is_set()
    assert backend.runtime.closed == 1
    with pytest.raises(BrowserRuntimeError):
        backend._browser_channel()
    assert len(starts) == 1


def test_grounding_guidance_and_desktop_channel_are_disabled(backend, monkeypatch):
    monkeypatch.setattr(module.HBackend, 'run_guidance', lambda *a: pytest.fail('Desktop guidance'))
    assert backend.run_guidance().declared.outcome == 'blocked'
    assert backend.locate('field').found is False
    assert backend.screen_matches('page')[0] is False
    with pytest.raises(BrowserRuntimeError):
        backend._desktop_channel()


def test_stop_event_is_shared_with_dispatcher_before_actor(backend, monkeypatch):
    stop = threading.Event()
    def run(self, bound, task, attempt, on_step, stop_event, on_lookup=None):
        assert self._bridge.operation_stop_event is stop_event
        return 'completed'
    monkeypatch.setattr(module.HBackend, 'run_attempt', run)
    assert backend.run_attempt(None, 'task', 0, None, stop) == 'completed'
    assert not stop.is_set()
    assert backend._bridge.stop_event.is_set()
    stop.set()
    assert backend.run_attempt(None, 'task', 0, None, stop).status == 'interrupted'


def test_concurrent_operation_is_rejected(backend):
    backend._operation_lock.acquire()
    try:
        assert backend.run_attempt(None, '', 1, None, threading.Event()).status == 'failed'
    finally:
        backend._operation_lock.release()


def test_event_mapping_never_calls_engine_overlay(monkeypatch):
    import hcs_agent.backend as engine
    monkeypatch.setattr(engine, '_agent_xy_to_screen', lambda *a: pytest.fail('Native overlay'))
    event = SimpleNamespace(type='AgentEvent', data={'kind': 'policy_event',
        'tool_reqs': [{'tool_name': 'click_web', 'args': {'x': 50, 'y': 100}}]})
    step = module._browser_event_step(event, 0, 1)
    assert step.detail['pointer'] is None
    assert step.detail['viewport_pointer'] == [50, 100]
    assert step.detail['coordinate_space'] == 'browser_viewport'


def test_prepare_episode_resets_without_opening_h_channel(backend):
    backend.prepare_episode()
    assert backend.runtime.reset is True
    assert backend._manager.started == []


@pytest.mark.parametrize('name,args', [
    ('input_text', {'text': '\ue009lfile:///private/secret'}),
    ('write_at', {'x': 1, 'y': 2, 'text': '\ue03dv'}),
    ('click_at', {'x': 1, 'y': 2, 'button': 'middle'}),
    ('click_at', {'x': 1, 'y': 2, 'button': 'right'}),
])
def test_text_cannot_smuggle_webdriver_keys_or_clipboard_gestures(bridge, name, args):
    assert bridge._dispatch(name, args) == (None, bridge.blocked_error)
    assert bridge._driver.calls == []


def test_failed_stream_cannot_leave_actor_running_on_reusable_channel(backend, monkeypatch):
    calls = []
    backend._client.sessions = SimpleNamespace(
        get_session_status=lambda sid, **kw: SimpleNamespace(status='running'),
        cancel_session=lambda sid, **kw: calls.append(('cancel', sid)))
    def run(self, bound, task, attempt, on_step, stop_event, on_lookup=None):
        return module.AttemptResult('owned-actor', 'failed', module.DeclaredResult(outcome='not_run'))
    monkeypatch.setattr(module.HBackend, 'run_attempt', run)
    result = backend.run_attempt(None, '', 0, None, threading.Event())
    assert result.status == 'failed' and 'termination' in result.error
    assert calls == [('cancel', 'owned-actor')]
    assert backend._poisoned and backend.runtime.closed == 1
    assert backend._bridge.stop_event.is_set()
    assert backend.run_attempt(None, '', 0, None, threading.Event()).status == 'failed'


def test_terminal_actor_can_be_followed_by_verification(backend, monkeypatch):
    backend._client.sessions = SimpleNamespace(get_session_status=lambda sid, **kw: SimpleNamespace(status='completed'))
    def run(self, bound, task, attempt, on_step, stop_event, on_lookup=None):
        return module.AttemptResult('owned-actor', 'completed', module.DeclaredResult(outcome='done'))
    monkeypatch.setattr(module.HBackend, 'run_attempt', run)
    assert backend.run_attempt(None, '', 0, None, threading.Event()).status == 'completed'
    assert not backend._poisoned and backend.runtime.closed == 0


def test_docs_lookup_required_only_for_actor_with_retriever(backend):
    backend.knowledge = SimpleNamespace(retrieval_method='hybrid')
    actor = backend._agent_spec('hcs-r01', 'Act')
    verifier = backend._agent_spec('hcs-verify-r01', 'Verify')
    assert 'use lookup_docs' in actor['instructions']
    assert 'never as authorization' in actor['instructions']
    assert 'lookup_docs' not in verifier['instructions']
    backend.knowledge = SimpleNamespace()
    assert 'lookup_docs' not in backend._agent_spec('hcs-r01', 'Act')['instructions']


@pytest.mark.parametrize('args', [{'hold_keys': None}, {'tap_keys': 'v'}, {'keys': None}])
def test_malformed_shortcut_is_rejected_without_exception(bridge, args):
    name = 'press_and_release_keys' if 'keys' in args else 'hold_and_tap_keys'
    assert bridge._dispatch(name, args) == (None, bridge.blocked_error)


def test_uncertain_verifier_cannot_leave_passing_checks_or_lose_session_id(backend, monkeypatch):
    backend._client.sessions = SimpleNamespace(
        get_session_status=lambda sid, **kw: SimpleNamespace(status='running'), cancel_session=lambda sid, **kw: None)
    def verify(self, bound, on_step, stop_event):
        return module.VerifyResult('owned-verifier', 'completed', {'all_good': True}, 'Looks good')
    def failed_cleanup(*args):
        raise TimeoutError('PRIVATE-detail')
    monkeypatch.setattr(module.HBackend, 'verify', verify)
    monkeypatch.setattr(backend._manager, 'stop', failed_cleanup)
    monkeypatch.setattr(backend.runtime, 'close', failed_cleanup)
    result = backend.verify(None, None, threading.Event())
    assert result.h_session_id == 'owned-verifier'
    assert result.status == 'failed' and result.checks == {}
    assert backend._poisoned and backend._bridge.stop_event.is_set()
    assert 'PRIVATE' not in result.error


def test_uncertain_session_creation_without_id_poisoned_before_retry(backend, monkeypatch):
    def run(self, bound, task, attempt, on_step, stop_event, on_lookup=None):
        return module.AttemptResult(None, 'failed', module.DeclaredResult(outcome='not_run'), error='start timeout')
    monkeypatch.setattr(module.HBackend, 'run_attempt', run)
    result = backend.run_attempt(None, '', 0, None, threading.Event())
    assert result.h_session_id is None and result.declared.outcome == 'blocked'
    assert backend._poisoned and backend.runtime.closed == 1


def test_command_diagnostics_contain_names_and_reasons_only(bridge):
    bridge._dispatch('scroll_at', {'x': 10, 'y': 20, 'dy': 200})
    bridge._dispatch('execute_script', {'script': 'PRIVATE-SENTINEL'})
    bridge._dispatch('PRIVATE-SENTINEL', {})
    bridge._dispatch('goto', {'url': 'https://user:PRIVATE-SENTINEL@example.com'})
    diagnostic = bridge.diagnostics()
    assert diagnostic['accepted_commands'] == {'scroll_at': 1}
    assert {'command': 'execute_script', 'reason': 'command_not_allowed', 'count': 1} in diagnostic['denied_commands']
    assert 'PRIVATE' not in str(diagnostic)
    assert 'example.com' not in str(diagnostic)


def test_h_validation_errors_are_visible_without_copying_arguments():
    event = SimpleNamespace(type='AgentEvent', data={'kind': 'policy_event', 'tool_reqs': [],
        'validation_errors': ["scroll_element should be an object, got PRIVATE-SENTINEL"]})
    step = module._browser_event_step(event, 2, 1)
    assert step.kind == 'error'
    assert step.detail == {'origin': 'h_tool_validation', 'category': 'scroll_element_schema', 'count': 1}
    assert 'PRIVATE' not in str(step)


def test_cancel_propagation_waits_with_gate_closed(backend):
    backend._browser_channel()
    backend._bridge.stop_event.set()
    states = iter(['idle', 'idle', 'idle', 'interrupted'])
    calls = []
    def status(sid, **kwargs):
        assert backend._bridge.stop_event.is_set()
        assert kwargs['request_options']['max_retries'] == 0
        return SimpleNamespace(status=next(states))
    backend._client.sessions = SimpleNamespace(get_session_status=status,
        cancel_session=lambda sid, **kw: calls.append(sid))
    assert backend._confirm_session_terminal('our-session') is True
    assert calls == ['our-session']
    assert backend._lifecycle_observations[-1]['status'] == 'interrupted'


def test_lifecycle_failure_preserves_original_business_explanation(backend, monkeypatch):
    backend._client.sessions = SimpleNamespace(
        get_session_status=lambda sid, **kw: SimpleNamespace(status='running'),
        cancel_session=lambda sid, **kw: None)
    def run(self, bound, task, attempt, on_step, stop_event, on_lookup=None):
        return module.AttemptResult('owned', 'failed', module.DeclaredResult(outcome='blocked',
            summary='Activity panel could not load', blocker='Offline', steps_taken=['Found opportunity']), error='Schema failure')
    monkeypatch.setattr(module.HBackend, 'run_attempt', run)
    result = backend.run_attempt(None, '', 0, None, threading.Event())
    assert result.declared.summary == 'Activity panel could not load'
    assert result.declared.steps_taken == ['Found opportunity']
    assert result.declared.blocker.startswith('Offline')
    assert result.error.startswith('Schema failure')


def test_scroll_instructions_avoid_stringified_scroll_element(backend):
    instructions = backend._agent_spec('actor', 'Act')['instructions']
    assert 'omitting scroll_element entirely' in instructions
    assert 'never a description string or JSON encoded as a string' in instructions
