"""Empty AX diagnostics are counters, not another export of the user's screen."""

import json
from types import SimpleNamespace

import pytest

from hcs_agent import a11y, cli
from hcs_agent.backend import HBackend


@pytest.fixture
def catalogue(monkeypatch):
    backend = object.__new__(HBackend)
    backend.use_a11y = backend.observe_only = True
    controls = [a11y.Candidate('AXButton', 'private-label', (10, 20, 60, 30)),
                a11y.Candidate('AXPopUpButton', 'private-other-label', (90, 20, 60, 30))]
    page = a11y.PageInfo('Devin', 'private-title', 'https://example.test/?private-token',
                        native=True, elements=controls, bundle_id='com.exafunction.windsurf')
    monkeypatch.setattr(a11y, 'page', lambda: page)
    monkeypatch.setattr(a11y, 'visible_at_point', lambda e: e is controls[1])
    return backend, page


def test_counts_distinguish_read_controls_from_covered_controls_without_contents(catalogue):
    backend, _ = catalogue
    _, items = backend.page_catalogue()
    assert len(items) == 1
    assert backend.last_catalogue_diagnostic == {
        'status': 'ready', 'raw': 2, 'eligible': 2, 'visible': 1, 'covered': 1,
        'native': True, 'is_front': True,
    }
    assert 'private' not in json.dumps(backend.last_catalogue_diagnostic)


@pytest.mark.parametrize('state,expected', [
    ('empty', 'tree_empty'), ('covered', 'controls_covered'),
    ('no-controls', 'no_usable_controls'), ('background', 'window_not_front'),
])
def test_empty_catalogues_keep_the_specific_reason(catalogue, monkeypatch, state, expected):
    backend, page = catalogue
    if state == 'empty':
        page.elements = []
    elif state == 'covered':
        monkeypatch.setattr(a11y, 'visible_at_point', lambda _: False)
    elif state == 'background':
        page.is_front = False
    else:
        page.elements = [a11y.Candidate('AXGroup', 'private-container', (0, 0, 800, 600))]
    _, items = backend.page_catalogue()
    assert items == [] and backend.last_catalogue_diagnostic['status'] == expected
    assert 'private' not in json.dumps(backend.last_catalogue_diagnostic)


def test_diagnostics_reset_and_never_include_framework_exception_details(catalogue, monkeypatch):
    backend, _ = catalogue
    backend.page_catalogue()
    monkeypatch.setattr(a11y, 'page', lambda: None)
    assert backend.page_catalogue() is None
    assert backend.last_catalogue_diagnostic['status'] == 'unavailable'
    assert backend.last_catalogue_diagnostic['raw'] == 0

    def failed():
        raise RuntimeError('private error details')

    monkeypatch.setattr(a11y, 'page', failed)
    assert backend.page_catalogue() is None
    assert backend.last_catalogue_diagnostic['status'] == 'read_failed'
    assert 'private' not in json.dumps(backend.last_catalogue_diagnostic)


def test_local_status_copies_only_the_saved_diagnostic(catalogue, monkeypatch):
    backend, _ = catalogue
    backend.page_catalogue()
    monkeypatch.setitem(cli._CONTROL, 'backend', backend)
    monkeypatch.setitem(cli._MAGNET, 'current', None)
    monkeypatch.setitem(cli._SPEECH, 'speaker', None)
    monkeypatch.setitem(cli._VOICE, 'ptt', None)
    diagnostic = cli._control_status()['accessibility']
    assert diagnostic == backend.last_catalogue_diagnostic
    backend.last_catalogue_diagnostic['status'] = 'unavailable'
    assert diagnostic['status'] == 'ready'
