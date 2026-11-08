import pytest

from pilot.creative_catalog import tasks_for


def test_public_probes_never_inherit_an_authenticated_profile_or_operator_answers():
    tasks = tasks_for('documentation', {'browser_profile_id': 'h-profile', 'software': 'h-company'})
    assert len(tasks) == 3
    for task in tasks:
        assert not task.authenticated
        assert task.comparison_family == 'documentation'
        assert not task.documentation_context  # the actor must read the actual page
        env = task.agent()['environments'][0]
        assert env['use_default_browser_profile'] is False
        assert 'English' in task.agent()['instructions']


@pytest.mark.parametrize('account', [{}, {'software': 'h-company', 'browser_profile_id': 'h-profile',
                                        'authentication_verified': True},
                                   {'software': 'comfyui', 'browser_profile_id': 'comfy-profile'}])
def test_cloud_probes_require_separately_verified_comfy_auth(account):
    with pytest.raises(ValueError):
        tasks_for('comfy-cloud', account)


def test_comfy_account_scope_stays_readonly_and_does_not_publish_entire_account():
    tasks = tasks_for('comfy-cloud', {'software': 'comfyui', 'browser_profile_id': 'comfy-profile',
                                    'authentication_verified': True})
    assert len(tasks) == 3
    for task in tasks:
        assert task.authenticated and task.allowed_origins == ('https://cloud.comfy.org',)
        assert task.display_allowed_paths == ()  # explicit scoped display policy needed for private frames
        assert 'Read only:' in task.agent()['instructions']
        assert task.mode == 'act' and task.purpose == 'capability_test'
