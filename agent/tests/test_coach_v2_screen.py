from unittest.mock import Mock
from datetime import datetime, timezone
import pytest
from hcs_agent import a11y, coach_v2_screen as screen
from hcs_agent.coach_v2 import CoachProtocolError

URL = 'https://platform.hcompany.ai/api-keys'


def page(*labels, url=URL):
    return a11y.PageInfo('Chrome', 'H Platform', url,
                        elements=[a11y.Candidate('AXStaticText', v, (0, 0, 100, 20)) for v in labels])


@pytest.mark.parametrize('value', [
    'hk-' + 'a123' * 12, 'sk_' + 'a123' * 12, 'aB19' * 12,
    'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.signature', '4242 4242 4242 4242'])
def test_secret_like_text_cannot_enter_targets_or_text(value):
    result = screen.sanitize_page(page('Create API key', value, 'h-hackathon', '1 day'))
    names = [c.name for c in result.elements]
    assert names == ['Create API key', 'h-hackathon', '1 day']
    assert value not in screen.public_text(value)


def test_input_values_are_never_requested_by_safe_observer(monkeypatch):
    attrs = []
    monkeypatch.setattr(a11y, 'available', lambda: True)
    monkeypatch.setattr(a11y, '_browser_window', lambda **_: ('window', 'Chrome', True))
    monkeypatch.setattr(a11y, '_web_area', lambda _: 'web')
    monkeypatch.setattr(a11y, '_attr', lambda _, key: attrs.append(key) or URL)
    monkeypatch.setattr(a11y, '_read_browser_page', lambda *a, **k: page('Create API key'))
    assert screen.read_page().url == URL
    assert set(attrs) == {'AXURL'}


@pytest.mark.parametrize('url', ['https://example.com', 'https://platform.hcompany.ai/vaults',
                                  'https://platform.hcompany.ai/api-keys?token=private'])
def test_blocked_identity_is_not_walked(monkeypatch, url):
    walk = Mock()
    monkeypatch.setattr(a11y, 'available', lambda: True)
    monkeypatch.setattr(a11y, '_browser_window', lambda **_: ('window', 'Chrome', True))
    monkeypatch.setattr(a11y, '_web_area', lambda _: 'web')
    monkeypatch.setattr(a11y, '_attr', lambda *_: url)
    monkeypatch.setattr(a11y, '_read_browser_page', walk)
    with pytest.raises(CoachProtocolError):
        screen.read_page()
    walk.assert_not_called()


def test_quota_only_fetched_for_relevant_question_and_cached(monkeypatch):
    quota = {'limit': 10, 'active': 2, 'available': 8, 'source': 'H sessions quota API'}
    fetch = Mock(return_value=quota)
    monkeypatch.setattr(screen, 'fetch_quota', fetch)
    monkeypatch.setattr(screen, '_quota_at', 0)
    monkeypatch.setattr(screen, '_quota_cache', None)
    original = {'url': URL}
    assert screen.attach_quota(original, 'Explain Skills') == original
    fetch.assert_not_called()
    assert screen.attach_quota(original, 'How many agent sessions can my current plan run at once?') == original
    fetch.assert_not_called()
    assert screen.attach_quota(original, 'How many agents can the Companion API connection run?')['account_quota'] == quota
    assert screen.attach_quota(original, 'Combien de sessions simultanées pour Companion API ?')['account_quota'] == quota
    assert 'account_quota' not in original
    fetch.assert_called_once()


def test_unavailable_quota_is_not_invented(monkeypatch):
    monkeypatch.setattr(screen, 'fetch_quota', Mock(side_effect=RuntimeError('provider failure')))
    monkeypatch.setattr(screen, '_quota_at', 0)
    assert 'account_quota' not in screen.attach_quota({'url': URL}, 'How many sessions can Companion API run?')


def creation_form(kind='skill'):
    heading = 'New skill' if kind == 'skill' else 'Create an API key'
    url = 'https://platform.hcompany.ai/skills' if kind == 'skill' else URL
    result = page(url=url)
    result.elements = [a11y.Candidate('AXHeading', heading, (200, 100, 200, 30))]
    return result


def test_only_allowlisted_fields_in_known_creation_form_have_values_read(monkeypatch):
    original = creation_form()
    candidates = [a11y.Candidate(role, label, (200, 150 + index * 60, 200, 40), ref=label)
                  for index, (role, label) in enumerate([
                      ('AXTextField', 'Name *'), ('AXTextArea', 'Description *'), ('AXTextArea', 'Body *'),
                      ('AXTextField', 'Source URL'), ('AXTextField', 'URL pattern'),
                      ('AXTextField', 'API token'), ('AXSecureTextField', 'Name *')])]
    # The real walker already excludes secure fields.
    monkeypatch.setattr(screen, '_walk_form_inputs', lambda *_: candidates[:-1])
    values = {'Name *': 'guided-onboarding', 'Description *': 'Coach one step at a time.',
              'Body *': '# Guided onboarding\nWait for the user to act.'}
    attr = Mock(side_effect=lambda ref, name: values.get(ref) if name == 'AXValue' else None)
    monkeypatch.setattr(a11y, '_attr', attr)
    enriched = screen.enrich_form_page(original, 'web')
    assert enriched.form_kind == 'skill'
    assert [f['field'] for f in enriched.form_fields] == ['name', 'description', 'body']
    assert [call.args[0] for call in attr.call_args_list] == ['Name *', 'Description *', 'Body *']
    assert enriched.form_fields[2]['value'] == values['Body *']
    assert original.elements == [original.elements[0]]


@pytest.mark.parametrize('url,heading', [
    ('https://platform.hcompany.ai/skills', 'Skills'),
    ('https://platform.hcompany.ai/api-keys', 'API keys'),
    ('https://platform.hcompany.ai/settings', 'Create an API key'),
    ('https://hub.hcompany.ai/skills', 'New skill'),
    ('https://platform.hcompany.ai/skills?token=private', 'New skill'),
])
def test_no_form_values_read_without_known_creation_context(monkeypatch, url, heading):
    original = page(url=url)
    original.elements = [a11y.Candidate('AXHeading', heading, (200, 100, 200, 30))]
    walk = Mock()
    monkeypatch.setattr(screen, '_walk_form_inputs', walk)
    assert screen.enrich_form_page(original, 'web') is original
    walk.assert_not_called()


def test_unlabelled_empty_field_is_recovered_from_exact_visible_label(monkeypatch):
    original = creation_form()
    original.elements.append(a11y.Candidate('AXStaticText', 'Body *', (200, 130, 100, 20)))
    field = a11y.Candidate('AXTextArea', '', (200, 160, 200, 100), ref='body')
    monkeypatch.setattr(screen, '_walk_form_inputs', lambda *_: [field])
    monkeypatch.setattr(a11y, '_attr', lambda ref, name: '' if name == 'AXValue' else None)
    enriched = screen.enrich_form_page(original, 'web')
    assert enriched.elements[-1].name == 'Body *'
    assert enriched.form_fields[0]['value'] == ''


def test_ambiguous_or_unrelated_field_does_not_get_a_neighbour_label(monkeypatch):
    original = creation_form()
    original.elements.extend([a11y.Candidate('AXStaticText', name, (200, y, 100, 20))
                              for name, y in [('Name *', 130), ('Description *', 150)]])
    candidates = [a11y.Candidate('AXTextArea', '', (200, 180, 200, 100), ref='empty'),
                  a11y.Candidate('AXTextField', 'API token', (200, 180, 200, 40), ref='token')]
    monkeypatch.setattr(screen, '_walk_form_inputs', lambda *_: candidates)
    attr = Mock(return_value=None)
    monkeypatch.setattr(a11y, '_attr', attr)
    assert screen.enrich_form_page(original, 'web').form_fields == []
    assert not any(call.args[1] == 'AXValue' for call in attr.call_args_list)


def test_expiry_popup_reads_its_selected_static_child_not_calendar_options(monkeypatch):
    original = creation_form('api_key')
    popup = a11y.Candidate('AXPopUpButton', 'Expiry', (200, 180, 200, 40), ref='popup')
    monkeypatch.setattr(screen, '_walk_form_inputs', lambda *_: [popup])
    data = {('popup', 'AXChildren'): ['selected', 'option'],
            ('selected', 'AXRole'): 'AXStaticText', ('selected', 'AXValue'): 'No expiry',
            ('option', 'AXRole'): 'AXCheckBox', ('option', 'AXValue'): '30 days'}
    attr = Mock(side_effect=lambda ref, name: data.get((ref, name)))
    monkeypatch.setattr(a11y, '_attr', attr)
    enriched = screen.enrich_form_page(original, 'web')
    assert enriched.form_fields[0]['value'] == 'No expiry'
    assert not any(call.args == ('option', 'AXValue') for call in attr.call_args_list)


def test_allowlisted_value_is_still_redacted_before_context(monkeypatch):
    original = creation_form()
    candidate = a11y.Candidate('AXTextField', 'Name *', (200, 150, 200, 40), ref='name')
    monkeypatch.setattr(screen, '_walk_form_inputs', lambda *_: [candidate])
    secret = 'hk-' + 'a123' * 12
    monkeypatch.setattr(a11y, '_attr', lambda *_: secret)
    enriched = screen.enrich_form_page(original, 'web')
    assert enriched.form_fields[0]['redacted']
    assert secret not in str(screen.observation_context(enriched))


def key_observation(expiry, name='h-hackathon-demo'):
    return {'form': {'kind': 'api_key', 'fields': [
        {'field': 'name', 'value': name, 'redacted': False},
        {'field': 'expiry', 'value': expiry, 'redacted': False},
    ]}}


@pytest.mark.parametrize('expiry,verified,reason', [
    ('24 hours', True, 'observed_relative_duration'),
    ('1 day', True, 'observed_relative_duration'),
    ('30 days', False, 'expiry_duration_mismatch'),
    ('No expiry', False, 'no_expiry'),
    ('Monday, 9 November 2026', False, 'date_only_cannot_verify_hours'),
    ('2026-11-09', False, 'date_only_cannot_verify_hours'),
    ('2026-11-09T12:00:00', False, 'expiry_time_not_verifiable'),
])
def test_key_confirmation_never_substitutes_no_expiry_or_date_for_24_hours(expiry, verified, reason):
    result = screen.verify_api_key_form(key_observation(expiry), 'h-hackathon-demo')
    assert result['verified'] is verified
    assert result['reason'] == reason


def test_key_confirmation_requires_matching_name_unique_fields_and_timezone():
    assert screen.verify_api_key_form(key_observation('24 hours', name='another-name'),
                                      'h-hackathon-demo')['reason'] == 'name_mismatch'
    observed = key_observation('24 hours')
    observed['form']['fields'].append({'field': 'name', 'value': 'h-hackathon-demo'})
    assert screen.verify_api_key_form(observed, 'h-hackathon-demo')['reason'] == 'name_not_observed'
    now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    assert screen.verify_api_key_form(key_observation('2026-11-09T13:00:00+01:00'),
                                      'h-hackathon-demo', now=now)['verified']
    assert not screen.verify_api_key_form(key_observation('2026-11-09T14:00:00+01:00'),
                                          'h-hackathon-demo', now=now)['verified']


def test_observation_clock_preserves_local_offset_and_field_values():
    now = datetime.fromisoformat('2026-11-08T23:45:00+01:00')
    original = creation_form()
    enriched = screen.FormPage(**original.__dict__, form_kind='skill',
                              form_fields=[{'field': 'name', 'label': 'Name *', 'value': '', 'redacted': False}])
    context = screen.observation_context(enriched, now=now)
    assert context['clock']['local_datetime'] == '2026-11-08T23:45:00+01:00'
    assert context['clock']['source'] == 'local_system_clock'
    assert context['form']['fields'][0]['value'] == ''
    assert '2026-11-08T23:45:00+01:00' in context['text'][0]
