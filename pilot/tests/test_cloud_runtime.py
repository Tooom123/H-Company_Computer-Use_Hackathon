"""Offline contracts for owned cloud sessions, quota and private live images."""
import base64
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

from PIL import Image
import pytest

from pilot.cloud_runtime import CloudCampaignRunner, CloudTask, _clean_json


def task(**overrides):
    return replace(CloudTask('HC01', 'h-company', 'Public docs', 'Read the documented browser configuration.',
                             'https://hub.hcompany.ai/agents-api/browser/configuration',
                             ('https://hub.hcompany.ai',)), **overrides)


def png():
    buffer = BytesIO()
    Image.new('RGB', (20, 10), 'green').save(buffer, format='PNG')
    return buffer.getvalue()


def observation(url='https://hub.hcompany.ai/agents-api/browser/configuration', image=None):
    return {'type': 'AgentEvent', 'timestamp': '2026-11-08T00:00:00Z', 'data': {
        'kind': 'observation_event', 'type': 'web', 'metadata': {'url': url},
        'image': image or {'type': 'base64', 'source': base64.b64encode(png()).decode()}}}


def policy(tool='click_web', args=None, errors=None):
    return {'type': 'AgentEvent', 'data': {'kind': 'policy_event',
            'tool_reqs': [] if errors else [{'tool_name': tool, 'args': args or {}}],
            'validation_errors': errors or []}}


def scoped_task(**overrides):
    page = 'https://platform.hcompany.ai/agents/sessions/approved-session'
    return task(start_url=page, allowed_origins=('https://platform.hcompany.ai', 'https://hub.hcompany.ai'),
                browser_profile_id='profile-test', display_allowed_paths=('/agents/sessions/approved-session',),
                allowed_page_urls=(page,), **overrides)


class FakeClient:
    def __init__(self, *, events=None, late_events=None, quota_active=3, gate=None):
        self.sessions = self
        self.events, self.late_events = events or [], late_events or []
        self.quota_active, self.gate = quota_active, gate
        self.starts, self.cancels, self.resource_requests = [], [], []
        self.states = {}
        self.quota_checked = threading.Event()
        self.lock = threading.Lock()
        self.answer = {'content': 'Observed documentation', 'summary': 'Observed documentation', 'outcome': 'unknown', 'complete': True}
        self.fail_create = self.fail_poll = self.fail_cancel = False

    def get_session_quota(self, **kwargs):
        self.quota_checked.set()
        with self.lock:
            active = self.quota_active + sum(s not in {'interrupted', 'completed'} for s in self.states.values())
        return {'scope': 'account', 'limit': 10, 'active': active, 'available': max(0, 10 - active)}

    def start_session(self, **kwargs):
        self.starts.append(kwargs)
        if self.fail_create:
            raise TimeoutError('Remote request may have succeeded; sensitive provider response')
        sid = f'h-{len(self.starts)}'
        with self.lock:
            self.states[sid] = 'working'
        return SimpleNamespace(id=sid)

    def get_session_changes(self, sid, from_index, **kwargs):
        if self.fail_poll:
            raise RuntimeError('Should never expose provider text')
        if self.gate and not self.gate.wait(.02):
            return None
        if self.states[sid] == 'working':
            self.states[sid] = 'idle'
            return {'first_index': 0, 'new_events': self.events, 'answer': self.answer}
        if from_index == len(self.events) and self.late_events:
            return {'first_index': from_index, 'new_events': self.late_events}
        return None

    def get_session_status(self, sid, **kwargs):
        return {'status': self.states[sid], 'steps': 3}

    def get_session(self, sid, **kwargs):
        return {'latest_answer': self.answer}

    def cancel_session(self, sid, **kwargs):
        self.cancels.append(sid)
        if self.fail_cancel:
            raise TimeoutError('Cancellation unavailable')
        self.states[sid] = 'interrupted'

    def get_session_resource(self, sid, bucket, key, **kwargs):
        self.resource_requests.append((sid, bucket, key))
        yield png()


@pytest.fixture
def runners(tmp_path):
    opened = []

    def make(client=None, **kwargs):
        root = (tmp_path / f'private-{len(opened)}').resolve()
        runner = CloudCampaignRunner(root, client or FakeClient(), simulated=True, poll_seconds=0, **kwargs)
        opened.append(runner)
        return runner

    yield make
    for runner in opened:
        runner.close()


def wait_for(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    assert predicate()


def test_cloud_configuration_has_no_local_bridge_or_implicit_profile():
    env = task().agent()['environments'][0]
    assert env['host'] == 'cloud' and env['kind'] == 'web'
    assert env['use_default_browser_profile'] is False
    assert env['persist_browser_profile'] is False
    assert env['mode'] == {'type': 'visual', 'width': 1280, 'height': 832, 'markdown': False}
    assert 'vault_id' not in env and 'browser_profile_id' not in env
    authenticated = task(vault_id='vault-test', browser_profile_id='profile-test')
    assert authenticated.agent()['environments'][0]['vault_id'] == 'vault-test'
    assert 'vault-test' not in authenticated.messages()
    assert 'omit the optional scroll_element argument entirely' in task().agent()['instructions']


@pytest.mark.parametrize('changes', [
    {'start_url': 'https://evil.test/'}, {'start_url': 'https://hub.hcompany.ai/?token=private'},
    {'allowed_origins': ('http://hub.hcompany.ai',)}, {'allowed_origins': ('https://hub.hcompany.ai/path',)},
    {'scenario_id': '../escape'}, {'max_steps': 101}, {'max_time_s': 601},
    {'mode': 'guide'}, {'purpose': 'human_coaching'},
    {'browser_profile_id': 'profile-test', 'display_allowed_paths': ('/',)},
    {'question': 'hk-' + 'a' * 30},
])
def test_task_rejects_invalid_scope_and_secret_prompts(changes):
    with pytest.raises(ValueError):
        task(**changes)


def test_requires_approval_and_retains_actor_vs_human_provenance(runners):
    client = FakeClient()
    runner = runners(client)
    with pytest.raises(ValueError):
        runner.submit(task())
    episode_id = runner.submit(task(), approved=True)
    result = runner.wait(episode_id, 3)
    assert result['state'] == 'interrupted'  # answered idle -> v2 cancellation frees quota
    assert result['completion_reason'] == 'answered_then_cancelled_for_terminal_confirmation'
    assert result['declared'] == client.answer
    assert result['verification'] is None and result['human_feedback'] is None
    assert result['ready_for_sft'] is False and result['simulated'] is True
    assert result['mode'] == 'act' and result['purpose'] == 'capability_test'
    assert result['h_session_id'] == client.cancels[0]
    report = json.loads((runner.root / episode_id / 'report.json').read_text())
    assert report['h_session_id'] == result['h_session_id']
    assert client.starts[0]['queue'] is False
    assert client.starts[0]['request_options']['max_retries'] == 0


def test_late_observation_is_drained_and_only_local_manifest_is_exposed(runners):
    image = {'type': 'url', 'source': 'https://agp.eu.hcompany.ai/api/v2/sessions/h-1/resources/screenshots/last.png?signature=private'}
    client = FakeClient(events=[observation()], late_events=[observation(image=image)])
    runner = runners(client)
    eid = runner.submit(task(), approved=True)
    result = runner.wait(eid, 3)
    manifest = json.loads((runner.root / eid / 'frames.json').read_text())
    assert result['frame_count'] == 2
    assert [frame['index'] for frame in manifest['frames']] == [0, 1]
    assert client.resource_requests == [('h-1', 'screenshots', 'last.png')]
    for frame in manifest['frames']:
        assert frame['display_allowed'] is True and frame['phase'] == 'working'
        assert (runner.root / eid / frame['path']).read_bytes() == png()
        assert frame['content_type'] == 'image/png' and len(frame['sha256']) == 64
    for filename in ('episode.json', 'events.jsonl', 'frames.json'):
        text = (runner.root / eid / filename).read_text()
        assert 'signature=' not in text and 'agp.eu' not in text
    assert (runner.root / eid / 'frames' / '000001.png').stat().st_mode & 0o777 == 0o600


def test_duplicate_provider_cursor_does_not_duplicate_frames(runners):
    runner = runners()
    eid = runner.submit(task(), approved=True)
    runner.wait(eid, 3)
    job = runner._jobs[eid]
    changes = {'first_index': 0, 'new_events': [observation()]}
    cursor, _ = runner._consume(job, task(), changes, 0)
    cursor, _ = runner._consume(job, task(), changes, cursor)
    assert cursor == 1 and job['frame_count'] == 1


@pytest.mark.parametrize('url,authenticated,display_paths,expected', [
    ('https://hub.hcompany.ai/login', False, (), 0),
    ('https://hub.hcompany.ai/vault', False, (), 0),
    ('https://hub.hcompany.ai/api-keys', False, (), 0),
    ('https://hub.hcompany.ai/agents-api/vaults/overview', False, (), 1),
    ('https://hub.hcompany.ai/agents-api/vaults/overview', True, (), 0),
    ('https://hub.hcompany.ai/workspace', True, (), 0),
    ('https://hub.hcompany.ai/workspace/demo', True, ('/workspace/demo',), 1),
    ('https://hub.hcompany.ai/workspace/demo-foreign', True, ('/workspace/demo',), 0),
])
def test_authentication_screens_are_hidden_by_default(runners, url, authenticated, display_paths, expected):
    client = FakeClient(events=[observation(url)])
    runner = runners(client)
    t = task(browser_profile_id='profile-test' if authenticated else None, display_allowed_paths=display_paths)
    eid = runner.submit(t, approved=True)
    assert runner.wait(eid, 3)['frame_count'] == expected


@pytest.mark.parametrize('login_url,auth_origins', [
    ('https://platform.hcompany.ai/auth/login', ()),
    ('https://accounts.google.com/v3/signin/identifier', ('https://accounts.google.com',)),
    ('https://accounts.google.com/interstitial', ('https://accounts.google.com',)),
])
def test_authentication_required_persistently_withholds_older_and_later_frames(runners, login_url, auth_origins):
    allowed_page = 'https://platform.hcompany.ai/sessions/demo'
    client = FakeClient(events=[observation(allowed_page), observation(login_url)],
                        late_events=[observation(allowed_page)])
    runner = runners(client)
    t = task(start_url=allowed_page, allowed_origins=('https://platform.hcompany.ai',),
             browser_profile_id='expired-profile', auth_origins=auth_origins,
             display_allowed_paths=('/sessions/demo',))
    eid = runner.submit(t, approved=True)
    result = runner.wait(eid, 3)
    assert result['phase'] == 'finished' and result['state'] == 'interrupted'
    assert result['authentication_required'] is True and result['display_blocked'] is True
    assert result['latest_frame'] is None and result['frame_count'] == 1
    folder = runner.root / eid
    manifest = json.loads((folder / 'frames.json').read_text())
    assert manifest['frames'] == [] and manifest['display_blocked'] is True
    assert (folder / 'frames/000001.png').read_bytes() == png()  # retained privately
    report = json.loads((folder / 'report.json').read_text())
    assert report['authentication_required'] is True and report['display_blocked'] is True


def test_unrelated_hidden_path_does_not_claim_profile_login_failed(runners):
    client = FakeClient(events=[observation('https://hub.hcompany.ai/agents-api/vaults/overview')])
    runner = runners(client)
    result = runner.wait(runner.submit(task(browser_profile_id='profile-test'), approved=True), 3)
    assert result['frame_count'] == 0
    assert result['authentication_required'] is False and result['display_blocked'] is False


def test_outside_origin_quarantines_entire_episode_and_cancels_owned_session(runners):
    client = FakeClient(events=[observation('https://outside.test/'), observation()])
    runner = runners(client)
    eid = runner.submit(task(), approved=True)
    result = runner.wait(eid, 3)
    assert result['scope_violation'] is True and result['phase'] == 'quarantine'
    assert result['frame_count'] == 0 and client.cancels == ['h-1']
    assert result['quarantined'] is True and (runner.root / eid / 'quarantine.json').exists()


@pytest.mark.parametrize('suffix', ['/agents/sessions/another-session', '/agents/sessions',
    '/agents/sessions/approved-session-other', '/agents/sessions/approved-session/../another',
    '/agents/sessions/%61pproved-session', '/agents/sessions/approved-session?token=private'])
def test_same_origin_other_page_quarantines_and_archives_only_owned(runners, suffix):
    t = scoped_task()
    client = FakeClient(events=[observation(t.start_url), observation('https://platform.hcompany.ai' + suffix)],
                        late_events=[observation(t.start_url)])
    client.states['foreign-session'] = 'working'
    exports = []
    def export(sid, folder):
        exports.append(sid)
        return {'archive_complete': True}
    runner = runners(client, exporter=export)
    eid = runner.submit(t, approved=True)
    result = runner.wait(eid, 3)
    assert result['state'] == 'interrupted' and result['phase'] == 'quarantine'
    assert result['policy_stop_reason'] == 'observation_outside_task_pages'
    assert result['scope_violation'] and result['quarantined']
    assert result['frame_count'] == 1 and result['latest_frame'] is None
    assert json.loads((runner.root / eid / 'frames.json').read_text())['frames'] == []
    assert client.cancels == ['h-1'] and client.states['foreign-session'] == 'working'
    assert exports == ['h-1'] and result['export_status'] == 'complete'


@pytest.mark.parametrize('event', [
    observation('https://platform.hcompany.ai/auth/login?redirect=%2Fagents%2Fsessions'),
    policy('go_to_web', {'url': 'https://platform.hcompany.ai/auth/login'}),
])
def test_scoped_auth_redirect_is_not_a_page_violation(runners, event):
    runner = runners(FakeClient(events=[event]))
    result = runner.wait(runner.submit(scoped_task(), approved=True), 3)
    assert result['scope_violation'] is False and result['quarantined'] is False
    if event['data']['kind'] == 'observation_event':
        assert result['authentication_required'] is True


def test_scoped_task_can_still_read_allowed_documentation_origin(runners):
    runner = runners(FakeClient(events=[observation()]))
    result = runner.wait(runner.submit(scoped_task(), approved=True), 3)
    assert not result['quarantined']


def test_previous_login_mask_does_not_disable_later_page_scope_monitor(runners):
    client = FakeClient(events=[observation('https://platform.hcompany.ai/auth/login'),
                               observation('https://platform.hcompany.ai/agents/sessions/other')])
    runner = runners(client)
    result = runner.wait(runner.submit(scoped_task(), approved=True), 3)
    assert result['authentication_required'] is True
    assert result['policy_stop_reason'] == 'observation_outside_task_pages' and result['quarantined']


@pytest.mark.parametrize('tool', ['web_fetch', 'web_search', 'run_command_desktop'])
@pytest.mark.parametrize('kind', ['policy_event', 'tool_result'])
def test_forbidden_tool_events_persist_quarantine(runners, tool, kind):
    call = {'tool_name': tool, 'args': {'url': 'https://hub.hcompany.ai/agents-api/overview', 'private': 'do-not-log-this'}}
    event = {'type': 'AgentEvent', 'data': {'kind': kind, **({'tool_reqs': [call]} if kind == 'policy_event' else {'tool_req': call})}}
    client = FakeClient(events=[observation(), event], late_events=[observation()])
    runner = runners(client)
    eid = runner.submit(task(), approved=True)
    result = runner.wait(eid, 3)
    assert result['policy_stop_reason'] == 'forbidden_tool_observed' and result['scope_violation']
    assert result['quarantined'] and result['phase'] == 'quarantine' and result['latest_frame'] is None
    assert client.cancels == ['h-1']
    assert 'do-not-log-this' not in (runner.root / eid / 'events.jsonl').read_text()


@pytest.mark.parametrize('url', ['https://platform.hcompany.ai/agents/sessions/other',
    'https://outside.test/', 'javascript:alert(1)',
    'view-source:https://platform.hcompany.ai/agents/sessions/approved-session'])
def test_navigation_intent_for_another_session_is_detected(runners, url):
    client = FakeClient(events=[policy('go_to_web', {'url':url})])
    runner = runners(client)
    result = runner.wait(runner.submit(scoped_task(), approved=True), 3)
    assert result['policy_stop_reason'] == 'navigation_outside_task_scope'
    assert client.cancels == ['h-1']


def schema_error(field='scroll_element', value='private-value'):
    return policy(errors=[f"Tool 'scroll_web' received invalid arguments: {value}\nValidation errors:\n  - {field}: Input should be a valid dictionary"])


def test_repeated_schema_errors_stop_without_claiming_scope_violation(runners):
    events = [observation(), schema_error(value='secret-1'),
              {'type':'AgentEvent','data':{'kind':'error_event'}},
              schema_error(value='secret-2'), schema_error(value='secret-3')]
    client = FakeClient(events=events, late_events=[observation()])
    runner = runners(client)
    eid = runner.submit(task(), approved=True)
    result = runner.wait(eid, 3)
    assert result['quarantined'] and result['phase'] == 'quarantine'
    assert result['policy_stop_reason'] == 'repeated_tool_schema_validation'
    assert result['scope_violation'] is False and client.cancels == ['h-1']
    assert json.loads((runner.root / eid / 'frames.json').read_text())['frames'] == []
    assert 'secret-' not in (runner.root / eid / 'events.jsonl').read_text()
    report = json.loads((runner.root / eid / 'report.json').read_text())
    assert report['quarantined'] and report['scope_violation'] is False


@pytest.mark.parametrize('break_event', [
    {'type': 'AgentEvent', 'data': {'kind': 'tool_result', 'tool_req': {'tool_name':'click_web','args':{}}, 'result':None}},
    schema_error(field='num_pixels'),
])
def test_schema_loop_streak_resets_after_progress_or_different_error(runners, break_event):
    client = FakeClient(events=[schema_error(), schema_error(), break_event, schema_error(), schema_error()])
    runner = runners(client)
    result = runner.wait(runner.submit(task(), approved=True), 3)
    assert not result['quarantined']


def test_interleaved_observations_metrics_and_policy_intent_do_not_reset_schema_loop(runners):
    client = FakeClient(events=[schema_error(), observation(),
        {'type':'MetricsUpdateEvent','data':{'metrics':{'steps':1}}},
        schema_error(), observation(), policy(), schema_error()])
    runner = runners(client)
    result = runner.wait(runner.submit(task(), approved=True), 3)
    assert result['policy_stop_reason'] == 'repeated_tool_schema_validation'
    assert result['quarantined'] and client.cancels == ['h-1']


@pytest.mark.parametrize('url', ['https://outside.test/anything',
    'https://hub.hcompany.ai/agents-api/%62rowser', 'https://hub.hcompany.ai/agents-api/../private',
    'https://hub.hcompany.ai/agents-api/browser?token=secret'])
def test_task_page_scope_rejects_ambiguous_bindings(url):
    with pytest.raises(ValueError):
        task(allowed_page_urls=(url,))


def test_string_answer_normalizes_for_consoles_and_preserves_catalog_provenance(runners):
    client = FakeClient()
    client.answer = 'Read-only documented answer'
    runner = runners(client)
    eid = runner.submit(task(catalog_version='sponsor-v1', comparison_family='documentation'), approved=True)
    result = runner.wait(eid, 3)
    assert result['declared'] == {'summary': client.answer, 'outcome': 'unknown'}
    assert result['catalog_version'] == 'sponsor-v1' and result['comparison_family'] == 'documentation'
    request = json.loads((runner.root / eid / 'request.json').read_text())
    assert request['catalog_version'] == 'sponsor-v1'


@pytest.mark.parametrize('url', [
    'https://agp.eu.hcompany.ai/api/v2/sessions/someone-else/resources/bucket/key',
    'https://evil.test/api/v2/sessions/h-1/resources/bucket/key',
    'https://agp.eu.hcompany.ai/api/v2/sessions/h-1/resources/bucket/%252e%252e/secret',
    'https://agp.eu.hcompany.ai:8443/api/v2/sessions/h-1/resources/bucket/key',
])
def test_resource_url_must_identify_owned_session_on_h_origin(runners, url):
    client = FakeClient()
    runner = runners(client)
    with pytest.raises(ValueError):
        runner._resource('h-1', {'type': 'url', 'source': url})
    assert not client.resource_requests


def test_cancellation_never_targets_an_unowned_session(runners):
    client = FakeClient()
    runner = runners(client)
    assert runner._cancel('someone-else') is False
    with pytest.raises(KeyError):
        runner.stop('someone-else')
    assert not client.cancels


def test_ambiguous_create_is_not_retried_and_blocks_later_starts(runners):
    client = FakeClient()
    client.fail_create = True
    runner = runners(client)
    eid = runner.submit(task(), approved=True)
    result = runner.wait(eid, 3)
    assert result['state'] == 'start_uncertain' and result['error_class'] == 'TimeoutError'
    assert runner.status()['start_uncertain'] is True and len(client.starts) == 1
    assert (runner.root / eid / 'report.json').exists()
    assert 'sensitive provider response' not in (runner.root / eid / 'episode.json').read_text()
    with pytest.raises(RuntimeError):
        runner.submit(task(), approved=True)


def test_failed_cancellation_is_not_claimed_terminal(runners):
    client = FakeClient()
    client.fail_cancel = True
    runner = runners(client)
    result = runner.wait(runner.submit(task(), approved=True), 3)
    assert result['state'] == 'termination_unconfirmed'
    assert result['declared'] == client.answer


def test_export_also_retains_failed_trials_without_provider_error_text(runners):
    client = FakeClient()
    client.fail_poll = True
    exports = []
    def export(sid, folder):
        exports.append((sid, folder))
        return {'archive_complete': True}
    runner = runners(client, exporter=export)
    eid = runner.submit(task(), approved=True)
    result = runner.wait(eid, 3)
    assert result['state'] == 'failed' and result['error_class'] == 'RuntimeError'
    assert result['export_status'] == 'complete' and exports[0][0] == 'h-1'
    assert 'Should never expose' not in (runner.root / eid / 'episode.json').read_text()


def test_quota_counts_local_sessions_once_and_respects_parallelism(runners):
    gate = threading.Event()
    client = FakeClient(gate=gate, quota_active=3)
    runner = runners(client, max_parallel=6)
    episodes = [runner.submit(task(scenario_id=f'HC{i:02}'), approved=True) for i in range(7)]
    try:
        wait_for(lambda: len(client.starts) == 6)
        assert runner.status()['running'] == 6  # active provider=9, not 9+6
        assert len(client.starts) == 6
    finally:
        gate.set()
    for eid in episodes:
        runner.wait(eid, 5)
    assert len(client.starts) == 7


def test_quota_other_jobs_reserve_capacity_even_when_parallelism_is_higher(runners):
    gate = threading.Event()
    client = FakeClient(gate=gate, quota_active=9)
    runner = runners(client, max_parallel=4)
    first = runner.submit(task(), approved=True)
    second = runner.submit(task(scenario_id='HC02'), approved=True)
    try:
        wait_for(lambda: len(client.starts) == 1)
        time.sleep(.08)
        assert len(client.starts) == 1
    finally:
        gate.set()
    runner.wait(first, 3)
    runner.wait(second, 3)
    assert len(client.starts) == 2


def test_stop_while_waiting_for_quota_does_not_create_session(runners):
    client = FakeClient(quota_active=10)
    runner = runners(client)
    eid = runner.submit(task(), approved=True)
    assert client.quota_checked.wait(2)
    runner.stop(eid)
    assert runner.wait(eid, 2)['state'] == 'interrupted'
    assert not client.starts


def test_recursive_redaction_keeps_json_shape_and_strips_token_queries():
    original = {'answer': 'x' * 60000, 'url': 'https://example.test/path?signature=secret',
                'api_key': 'not-a-pattern', 'nested': ['hk-' + 'x' * 30]}
    clean = _clean_json(original)
    assert len(clean['answer']) == 50000
    assert clean['url'] == 'https://example.test/path'
    assert clean['api_key'] == '[secret removed]'
    assert clean['nested'] == ['[secret removed]']


def test_private_storage_rejects_git_and_symlink_roots(tmp_path):
    (tmp_path / '.git').mkdir()
    with pytest.raises(ValueError):
        CloudCampaignRunner((tmp_path / 'trace').resolve(), FakeClient())
    other = tmp_path / 'alias'
    other.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        CloudCampaignRunner(other, FakeClient())


@pytest.mark.parametrize('cap', [0, -1, 11, True, 1.5])
def test_invalid_concurrency_cap_fails_closed(tmp_path, cap):
    with pytest.raises(ValueError):
        CloudCampaignRunner(tmp_path.resolve(), FakeClient(), concurrency_cap=cap)
