"""Operator boundaries and private cloud launch gating; no external API calls."""
from fastapi.testclient import TestClient
import pytest

from pilot.cloud_server import create_cloud_app


class Runner:
    def __init__(self):
        self.tasks = []
        self.parallel = 2

    def status(self):
        return {'running': 0, 'queued': 0, 'simulated': True, 'max_parallel': self.parallel}

    def set_parallelism(self, value):
        self.parallel = value

    def submit(self, task, approved=False):
        assert approved is True
        self.tasks.append(task)
        return f'cloud_{len(self.tasks):016x}'

    def snapshot(self, identifier):
        if identifier != 'cloud_0000000000000001':
            raise KeyError(identifier)
        return {'id': identifier, 'state': 'completed'}

    def stop(self, identifier):
        return self.snapshot(identifier)

    def list_episodes(self):
        return []


class Knowledge:
    def list_documents(self):
        return []

    def search(self, query, top_k=6):
        return [{'citation_uri': 'knowledge://h-company/example/sha#0', 'section': 'Browser configuration',
                 'text': 'Use an explicit start_url and an environment of kind web.'}]


@pytest.fixture
def setup(tmp_path):
    runner = Runner()
    app = create_cloud_app(private_root=tmp_path, token='offline-test-token', runner=runner,
                           knowledge=Knowledge(), username='support', password='offline-test-company-password')
    client = TestClient(app, base_url='http://127.0.0.1:8771')
    client.headers['Authorization'] = 'Bearer offline-test-token'
    return client, runner, tmp_path


def test_no_launch_without_strict_approval_and_valid_cases(setup):
    client, runner, _ = setup
    assert client.post('/cloud/campaigns', json={'scenario_ids': ['HC01']}).status_code == 409
    assert client.post('/cloud/campaigns', json={'scenario_ids': ['HC01'], 'approved': 'yes'}).status_code == 422
    assert client.post('/cloud/campaigns', json={'scenario_ids': ['HC01', 'bogus'], 'approved': True}).status_code == 422
    assert client.post('/cloud/campaigns', json={'scenario_ids': ['HC01', 'HC01'], 'approved': True}).status_code == 422
    assert not runner.tasks


def test_public_campaign_no_oracle_or_implicit_auth(setup):
    client, runner, _ = setup
    status = client.get('/cloud/status').json()
    assert status['profile_configured'] is False and status['authentication_verified'] is False
    result = client.post('/cloud/campaigns', json={'scenario_ids': ['HC01', 'HC02'], 'approved': True, 'max_parallel': 6})
    assert result.status_code == 200
    assert len(runner.tasks) == 2 and runner.parallel == 6
    assert result.json()['purpose'] == 'capability_test'
    assert all(t.browser_profile_id is None and t.mode == 'act' for t in runner.tasks)
    assert 'expected_criteria' not in str(client.get('/cloud/scenarios').json())
    assert runner.tasks[0].documentation_context == ''


def test_authenticated_case_does_not_start_public_prefix_if_unbound(setup):
    client, runner, _ = setup
    assert client.post('/cloud/campaigns', json={'scenario_ids': ['HC01', 'HC07'], 'approved': True}).status_code == 422
    assert not runner.tasks


def test_retrieval_is_opt_in_and_preserves_source_in_actor_context(setup):
    client, runner, _ = setup
    result = client.post('/cloud/campaigns', json={'scenario_ids': ['HC01'], 'approved': True, 'use_knowledge': True})
    assert result.status_code == 200
    assert 'knowledge://h-company/' in runner.tasks[0].documentation_context
    assert 'expected_criteria' not in runner.tasks[0].documentation_context


def test_authenticated_page_scope_comes_only_from_each_cases_bindings(tmp_path):
    first = '11111111-1111-4111-8111-111111111111'
    second = '22222222-2222-4222-8222-222222222222'
    one = 'https://platform.hcompany.ai/agents/sessions/' + first
    two = 'https://platform.hcompany.ai/agents/sessions/' + second
    bindings = {'session_id': first, 'session_url': one}
    account = {'browser_profile_id': 'explicit-profile',
               'display_allowed_paths': ['/agents/sessions/unrelated-account-session'],
               'bindings': {'HC07': bindings, 'HC09': {**bindings, 'comparison_session_id': second, 'comparison_session_url': two}}}
    runner = Runner()
    app = create_cloud_app(private_root=tmp_path, token='offline-test-token', runner=runner,
        knowledge=Knowledge(), username='support', password='offline-password', account_configuration=account)
    client = TestClient(app, base_url='http://127.0.0.1:8771')
    client.headers['Authorization'] = 'Bearer offline-test-token'
    response = client.post('/cloud/campaigns', json={'scenario_ids':['HC07','HC09'], 'approved':True})
    assert response.status_code == 200, response.text
    assert runner.tasks[0].allowed_page_urls == (one,)
    assert set(runner.tasks[1].allowed_page_urls) == {one,two}
    assert runner.tasks[0].display_allowed_paths == ('/agents/sessions/' + first,)
    assert 'unrelated-account-session' not in str(runner.tasks[1].display_allowed_paths)


@pytest.mark.parametrize('extra', [{'Origin': 'http://evil.test'}, {'Host': 'evil.test'}, {'Authorization': 'Bearer nope'}])
def test_operator_boundary(setup, extra):
    client, _, _ = setup
    assert client.get('/cloud/status', headers=extra).status_code == 401


def test_company_auth_independent_of_operator_and_has_navigation(setup):
    client, _, _ = setup
    assert client.get('/company').status_code == 401
    assert client.get('/company/live').status_code == 401
    assert client.get('/companyish').status_code == 404
    auth = ('support', 'offline-test-company-password')
    assert client.get('/company', auth=auth).status_code == 200
    assert client.get('/company/live', auth=auth).status_code == 200
    assert client.get('/cloud/status', auth=auth).status_code == 401


def test_feedback_cannot_be_fabricated_by_default_or_overwritten(setup):
    client, _, root = setup
    folder = root / 'cloud/episodes/cloud_0000000000000001'
    folder.mkdir(parents=True)
    path = '/cloud/episodes/cloud_0000000000000001/feedback'
    value = {'success': 'partial', 'useful': 'unknown'}
    assert client.post(path, json=value).status_code == 409
    result = client.post(path, json={**value, 'confirmed_by_human': True})
    assert result.status_code == 200 and result.json()['label_source'] == 'human'
    assert result.json()['ready_for_sft'] is False and result.json()['training_consent'] is False
    assert client.post(path, json={**value, 'confirmed_by_human': True}).status_code == 409
