"""Keep interrupted attempts and independent judgments in the private campaign index."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def script(name):
    path = Path(__file__).resolve().parents[2] / 'scripts' / name
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_interrupted_episode_remains_in_campaign_index(tmp_path, monkeypatch):
    batch = script('run-rich-batch.py')
    private = tmp_path / 'private'
    private.mkdir()
    (private / 'pilot-token').write_text('offline-test')
    command = tmp_path / 'command.json'
    command.write_text('["fake-read-only-status"]')
    monkeypatch.setattr(batch.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=json.dumps({
        'odoo': {'database': 'holo_hackathon_rich', 'rich': {
            'snapshot': 'same', 'expected_snapshot': 'same', 'counts': {}, 'expected_counts': {}}}})))
    stopped = False
    def request(req, **kwargs):
        nonlocal stopped
        path = req.full_url.removeprefix('http://127.0.0.1:8767')
        if path == '/pilot/status':
            value = {'busy': False, 'environment': {'id': 'odoo-rich-v2.1'}}
        elif path == '/pilot/scenarios':
            value = [{'id': 'R01', 'requires_reference': False, 'prompt': 'Read only'}]
        elif path == '/pilot/episodes':
            value = {'session_id': 'test-session', 'state': 'awaiting_approval'}
        elif path.endswith('/approve'):
            value = {}
        elif path.endswith('/stop'):
            stopped = True
            value = {}
        elif stopped:
            value = {'state': 'stopped', 'pilot': {'export_status': 'pending'}}
        else:
            raise KeyboardInterrupt()
        return io.BytesIO(json.dumps(value).encode())
    monkeypatch.setattr(batch.urllib.request, 'urlopen', request)
    monkeypatch.setattr('sys.argv', ['run-rich-batch.py', '--private-root', str(private),
        '--campaign', 'interrupted', '--scenarios', 'R01', '--approve-read-only',
        '--state-check-command', str(command)])
    with pytest.raises(KeyboardInterrupt):
        batch.main()
    rows = json.loads((private / 'campaigns/interrupted/results.json').read_text())
    assert len(rows) == 1
    assert rows[0]['session_id'] == 'test-session'
    assert rows[0]['state'] == 'stopped'
    assert rows[0]['interruption'] == 'KeyboardInterrupt'
    assert rows[0]['human_feedback'] is None


def test_summary_keeps_scope_and_human_separate_and_counts_final_usage_once(tmp_path):
    summarize = script('summarize-rich-campaign.py').summarize
    episode = tmp_path / 'episodes/test-session'
    archive = tmp_path / 'archives/test-session/h-session'
    episode.mkdir(parents=True)
    archive.mkdir(parents=True)
    (episode / 'episode.json').write_text(json.dumps({'scenario_id': 'R01'}))
    (episode / 'agent-review.json').write_text(json.dumps({
        'task_success_agent': 'success', 'scope_compliance_agent': 'failure'}))
    (episode / 'labels.json').write_text(json.dumps({'task_success_user': 'success', 'user_confirmed': False}))
    usage = {'usage_per_model': [{'name': 'holo4', 'input_tokens': 100, 'cached_tokens': 40,
                                  'output_tokens': 20, 'reasoning_tokens': 5}]}
    for name in ['status-before.json', 'status-after.json']:
        (archive / name).write_text(json.dumps(usage))
    row = summarize(tmp_path)[0]
    assert row['agent_verdict'] == 'success'
    assert row['scope_compliance_agent'] == 'failure'
    assert row['human_verdict'] is None
    assert row['usage_per_model']['holo4'] == {
        'input_tokens': 100, 'cached_tokens': 40, 'output_tokens': 20, 'reasoning_tokens': 5}
    assert row['ready_for_sft'] is False
