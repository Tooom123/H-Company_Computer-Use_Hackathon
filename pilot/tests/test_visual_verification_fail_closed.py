"""Real GUIDE fast-verifier integration, with no screenshot or model call."""

import threading
from types import SimpleNamespace

import pytest

from hcs_agent.backend import HBackend, VerifyResult
from hcs_agent.runner import Intervention
from pilot.browser_backend import BrowserHBackend
from pilot.desktop_backend import DesktopConnectionError, PilotHBackend


@pytest.fixture
def desktop(monkeypatch):
    backend = object.__new__(PilotHBackend)
    monkeypatch.setattr(backend, '_require_chrome', lambda: None)
    return backend


def broken_grounder(*args):
    raise RuntimeError('private diagnostic that must not appear in a trace')


@pytest.mark.parametrize('method', ['effect_visible', 'screen_matches'])
def test_desktop_grounding_exception_never_confirms_an_observation(desktop, monkeypatch, method):
    monkeypatch.setattr(desktop, '_grounding', broken_grounder)
    matched, visible = getattr(desktop, method)('Odoo shows the expected value')
    assert matched is False
    assert desktop.last_visual_check['status'] == 'unavailable'
    assert 'inconclusif' in desktop.last_visual_check['message']
    assert 'private diagnostic' not in visible + str(desktop.last_visual_check)


@pytest.mark.parametrize('bad_result', [None, (True,), ('yes', 'Odoo'), (True, None), (True, '')])
def test_malformed_or_evidenceless_screen_check_is_inconclusive(desktop, monkeypatch, bad_result):
    monkeypatch.setattr(desktop, '_grounding', lambda: SimpleNamespace(effect_visible=lambda _: bad_result))
    assert desktop.effect_visible('result') == (False, '')
    assert desktop.last_visual_check['status'] == 'unavailable'


@pytest.mark.parametrize('matched', [True, False])
def test_real_observation_is_preserved(desktop, monkeypatch, matched):
    observed = (matched, 'Odoo displays the product page')
    monkeypatch.setattr(desktop, '_grounding', lambda: SimpleNamespace(effect_visible=lambda _: observed))
    assert desktop.effect_visible('expected result') == observed
    assert desktop.last_visual_check == {'check': 'effect_visible', 'status': 'observed', 'matched': matched}


def test_off_scope_check_does_not_capture_the_desktop(desktop, monkeypatch):
    monkeypatch.setattr(desktop, '_require_chrome', lambda: (_ for _ in ()).throw(DesktopConnectionError('off scope')))
    monkeypatch.setattr(desktop, '_grounding', lambda: pytest.fail('Unexpected desktop capture'))
    assert desktop.effect_visible('result') == (False, '')


def test_focus_change_during_check_discards_even_a_positive_result(desktop, monkeypatch):
    calls = []
    def guard():
        calls.append(1)
        if len(calls) == 2:
            raise DesktopConnectionError('focus changed')
    monkeypatch.setattr(desktop, '_require_chrome', guard)
    monkeypatch.setattr(desktop, '_grounding', lambda: SimpleNamespace(effect_visible=lambda _: (True, 'Odoo result')))
    assert desktop.effect_visible('result') == (False, '')


def test_browser_never_inherits_desktop_fail_open(monkeypatch):
    backend = object.__new__(BrowserHBackend)
    monkeypatch.setattr(backend, '_grounding', lambda: pytest.fail('Browser touched desktop grounding'))
    assert backend.effect_visible('result') == (False, '')
    assert backend.last_visual_check['status'] == 'unavailable'


@pytest.mark.skipif(not hasattr(Intervention, '_fast_verify'), reason='Older engine has no GUIDE fast verifier')
def test_latest_runner_falls_back_instead_of_manufacturing_success(desktop, monkeypatch):
    monkeypatch.setattr(desktop, '_grounding', broken_grounder)
    runner = object.__new__(Intervention)
    runner.backend, runner._stop = desktop, threading.Event()
    runner._trace = lambda message: None
    bound = SimpleNamespace(checks={'product_price': 'Product price is 10 EUR'})
    assert runner._fast_verify(bound) is None
    # Non-empty diagnostics used to be misread as another app and keep a guide
    # waiting on this same step. Unavailable now follows the bounded "no" path.
    assert runner._screen_shows('Price is 10 EUR', tries=1, software='odoo') == 'no'


def test_unavailable_full_verifier_preserves_the_inconclusive_diagnostic(desktop, monkeypatch):
    monkeypatch.setattr(desktop, '_grounding', broken_grounder)
    desktop.effect_visible('result')
    monkeypatch.setattr(HBackend, 'verify', lambda *a, **kw: VerifyResult(None, 'failed', error='Verification unavailable'))
    result = desktop.verify()
    assert not result.checks
    assert 'inconclusif' in result.observed


def test_independent_full_verification_can_still_confirm_real_evidence(desktop, monkeypatch):
    monkeypatch.setattr(desktop, '_grounding', broken_grounder)
    desktop.effect_visible('result')
    verified = VerifyResult('owned-verifier', 'completed', {'price': True}, 'Odoo product price is 10 EUR')
    monkeypatch.setattr(HBackend, 'verify', lambda *a, **kw: verified)
    assert desktop.verify() is verified
    assert verified.checks == {'price': True}
    assert 'inconclusif' not in verified.observed
