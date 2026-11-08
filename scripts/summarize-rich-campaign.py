#!/usr/bin/env python3
"""Aggregate private rich episodes, preserving engine/AI/human verdicts separately."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path


def load(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def summarize(root):
    rows = []
    for directory in sorted((root / 'episodes').iterdir()):
        episode = load(directory / 'episode.json')
        if not str(episode.get('scenario_id', '')).startswith('R'):
            continue
        report = load(directory / 'report.json')
        review = load(directory / 'agent-review.json')
        quarantine = load(directory / 'quarantine.json')
        human = load(directory / 'labels.json')
        timing = report.get('timings', {})
        duration = None
        if timing.get('approved_at') and timing.get('finished_at'):
            duration = (datetime.fromisoformat(timing['finished_at'].replace('Z', '+00:00')) -
                        datetime.fromisoformat(timing['approved_at'].replace('Z', '+00:00'))).total_seconds()
        usage = {}
        # Only status-after for each distinct H session; before/after must not be summed.
        for path in (root / 'archives' / directory.name).glob('*/status-after.json'):
            for model in load(path).get('usage_per_model', []):
                totals = usage.setdefault(model['name'], {})
                for key in ('input_tokens', 'cached_tokens', 'output_tokens', 'reasoning_tokens'):
                    if isinstance(model.get(key), (int, float)):
                        totals[key] = totals.get(key, 0) + model[key]
        rows.append({
            'session_id': directory.name, 'scenario_id': episode['scenario_id'],
            'created_at': episode.get('created_at'), 'environment': episode.get('environment'),
            'engine_revision': episode.get('engine_revision'), 'state': episode.get('state'),
            'engine_verification': report.get('verification', {}).get('satisfied'),
            'agent_verdict': review.get('task_success_agent', 'pending'),
            'scope_compliance_agent': review.get('scope_compliance_agent', 'unknown'),
            'agent_review_rationale': review.get('rationale', []),
            'quarantine_status': quarantine.get('status'),
            'human_verdict': human.get('task_success_user') if human.get('user_confirmed') else None,
            'human_useful': human.get('useful') if human.get('user_confirmed') else None,
            'duration_s': round(duration, 3) if duration is not None else None,
            'usage_per_model': usage or None, 'cost_usd_reported': report.get('cost_usd'),
            'archive_status': episode.get('export_status'), 'ready_for_sft': False,
        })
    return sorted(rows, key=lambda r: r['created_at'] or '')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    root, output = args.private_root.expanduser().resolve(), args.output.expanduser().resolve()
    if any((p / '.git').exists() for p in (output.parent, *output.parents)):
        parser.error('Private session-level summary must stay outside Git.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'episodes': summarize(root), 'ready_for_sft': False,
        'usage_note': 'Cached and reasoning fields are retained separately, not added to input/output.'},
        ensure_ascii=False, indent=2) + '\n')
    output.chmod(0o600)
    print(str(output))


if __name__ == '__main__':
    main()
