from unittest.mock import Mock
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
