"""Readable coaching notes and no provider code in user-facing action narration."""
from types import SimpleNamespace
import sys

import pytest

from hcs_agent.presentation import action_narration, paginate_text


@pytest.mark.parametrize('tools, expected', [
    (['write_desktop'], 'Entering text…'),
    (['write_at_desktop'], 'Filling in a field…'),
    (['click_desktop'], 'Selecting an on-screen control…'),
    (['wait_desktop'], 'Waiting for the page…'),
    (['answer'], 'Preparing the response…'),
    (['unknown_tool(secret)'], 'Working on the current step…'),
])
def test_action_types_have_plain_english_narration(tools, expected):
    assert action_narration(tools) == expected


def test_raw_action_remains_in_trace_but_never_reaches_overlay_or_desktop(monkeypatch, capsys):
    from hcs_agent import cli
    raw = "write_desktop({'content': 'private test content', 'overwrite': True})"
    event = SimpleNamespace(type='step', event_id='fixture-action', simulated=True, message=raw,
                            data={'step': {'kind': 'action', 'detail': {
                                'tools': ['write_desktop'], 'element': raw, 'pointer': None}}})
    monkeypatch.setattr(cli, '_LAST_ACTION', {})
    cli._print_event(event)
    assert cli._LAST_ACTION['summary'] == 'Entering text…'
    assert 'private test content' not in str(cli._LAST_ACTION)
    assert event.message == raw  # preserve the original evidence
    assert raw in capsys.readouterr().out


@pytest.mark.parametrize('text', [
    'One sentence. A second sentence must remain complete, including this final word.',
    'An extremely long URL: https://example.org/' + 'unbroken-path' * 30,
    'Read the answer.\n\nThen examine the last action.\nThe result remains unverified.',
    'Une phrase accentuée — and another language 日本語.',
])
def test_pagination_preserves_every_character_including_long_words(text):
    pages = paginate_text(text, lambda s: len(s) <= 35)
    assert ''.join(pages) == text
    assert all(0 < len(p) <= 35 for p in pages)


def test_note_page_prefers_a_complete_sentence_when_it_fits():
    text = 'Read the answer. Then look at the last action.'
    assert paginate_text(text, lambda s: len(s) <= 28)[0] == 'Read the answer. '


@pytest.mark.skipif(sys.platform != 'darwin', reason='Real AppKit font metrics')
@pytest.mark.parametrize('width,height', [(1470, 956), (800, 600), (600, 500)])
def test_long_notes_fit_real_font_metrics_without_losing_the_last_sentence(width, height):
    from hcs_agent.overlay import Scene, _scene_pages, _measure, _note_width
    text = ('The cloud browser works separately from your Mac. '
            'Read the configuration example before starting your session. ') * 8 + 'This is the final sentence.'
    pages, seconds = _scene_pages(Scene(text=text, step=12, why='Read the configuration before you run anything.'), width, height)
    assert ''.join(p.text for p in pages) == text
    assert len(pages) > 1 and len(seconds) == len(pages)
    for p in pages:
        _, _, tw, th = _measure('12. ' + p.text, 19, _note_width(width))
        _, _, ww, wh = _measure(p.why, 14, _note_width(width, 420))
        assert tw + 20 + 28 <= width
        assert th + wh + 46 + 28 <= height
    assert 'final page' in pages[-1].why


@pytest.mark.skipif(sys.platform != 'darwin', reason='Native overlay binding')
def test_moving_target_does_not_restart_paginated_note(monkeypatch):
    from hcs_agent import overlay
    ov = overlay.Overlay.__new__(overlay.Overlay)
    ov._screen_h, ov._seed, ov.hold_reveal = 956, 1, None
    ov.window = SimpleNamespace(orderFrontRegardless=lambda: None)
    ov.view = SimpleNamespace(scene=None, bounds=lambda: SimpleNamespace(size=SimpleNamespace(width=1470, height=956)),
                              setNeedsDisplay_=lambda _: None)
    monkeypatch.setattr(overlay, '_on_main', lambda f: f())
    text = 'Read the response and check the evidence. ' * 30
    scene = overlay.Scene(text=text, target=(50, 100))
    ov.show_scene(scene)
    assert ov.view.scene.text == text
    assert len(ov.view.page_scenes) > 1
    ov.view.page_index, ov.view.page_started_at = 1, 42
    ov.show_scene(overlay.replace(scene, target=(80, 120)), animate=False)
    assert ov.view.page_index == 1 and ov.view.page_started_at == 42
    assert ov.view.page_scenes[1].target == (80, 836)
    assert ov.reading_duration > 10


@pytest.mark.skipif(sys.platform != 'darwin', reason='Native overlay binding')
def test_page_timer_waits_for_reveal_and_stops_at_last_page(monkeypatch):
    from hcs_agent import overlay
    clock, redraws = [10], []
    monkeypatch.setattr(overlay.time, 'monotonic', lambda: clock[0])
    ov = overlay.Overlay.__new__(overlay.Overlay)
    ov.view = SimpleNamespace(scene=overlay.Scene(text='Long answer'), held=True,
                              page_scenes=[object(), object()], page_seconds=[5, 5],
                              page_index=0, page_started_at=None,
                              setNeedsDisplay_=redraws.append)
    ov._advance_page()
    assert ov.view.page_started_at is None
    ov.view.held = False
    ov._advance_page()
    clock[0] += 6
    ov._advance_page()
    assert ov.view.page_index == 1 and redraws == [True]
    clock[0] += 6
    ov._advance_page()
    assert ov.view.page_index == 1 and redraws == [True]
