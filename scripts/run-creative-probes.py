#!/usr/bin/env python3
"""Run bounded H cloud probes, archiving in the existing private control tower.

Default is a dry run. --execute spends H API credits. Each suite has three
read-only cases; --parallel=3 uses separate browsers, not separate user accounts.
Comfy Cloud requires a verified Comfy-only profile in a private JSON file.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot.creative_catalog import CASES, tasks_for


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['documentation', 'comfy-cloud', 'comfy-public'], default='documentation')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--parallel', type=int, choices=range(1, 4), default=3)
    parser.add_argument('--private-root', type=Path, default=Path.home() / 'Library/Application Support/HCompanionResearch/cloud-pilot')
    parser.add_argument('--account-file', type=Path)
    parser.add_argument('--case', action='append', choices=[c['id'] for c in CASES],
                        help='Run only these cases from the selected suite (repeatable).')
    args = parser.parse_args()
    account = {}
    if args.account_file:
        path = args.account_file.expanduser().resolve()
        if any((p / '.git').exists() for p in (path.parent, *path.parents)):
            parser.error('Account profile configuration must remain outside Git.')
        account = json.loads(path.read_text())
    try:
        tasks = tasks_for(args.suite, account)
    except ValueError as error:
        parser.error(str(error))
    if args.case:
        if not set(args.case).issubset({t.scenario_id for t in tasks}):
            parser.error('Every selected case must belong to the selected suite.')
        tasks = [t for t in tasks if t.scenario_id in args.case]
    print(json.dumps({'suite': args.suite, 'execute': args.execute,
                      'parallel': args.parallel, 'scenarios': [t.scenario_id for t in tasks]}), flush=True)
    if not args.execute:
        return
    os.umask(0o077)
    from dotenv import dotenv_values
    from hai_agents import Client
    from pilot.cloud_runtime import CloudCampaignRunner
    key = dotenv_values(ROOT / 'app/.env').get('HAI_API_KEY')
    if not key:
        parser.error('Missing HAI_API_KEY in app/.env.')
    spec = importlib.util.spec_from_file_location('creative_archive', ROOT / 'scripts/trace_export_h.py')
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
    resources = archive.CloudClient(key)

    def export(sid, folder):
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        return archive.archive_session(resources, sid, folder)

    runner = CloudCampaignRunner(args.private_root.expanduser().resolve(), Client(api_key=key),
                                 max_parallel=args.parallel, exporter=export)
    identifiers = []
    try:
        for task in tasks:
            identifier = runner.submit(task, approved=True)
            identifiers.append(identifier)
            criteria = next(c['criteria'] for c in CASES if c['id'] == task.scenario_id)
            (runner.root / identifier / 'operator-criteria.json').write_text(json.dumps({
                'criteria': criteria, 'actor_received_criteria': False, 'human_guidance_validated': False,
                'label_status': 'pending_independent_review'}, indent=2) + '\n')
            print(json.dumps({'id': identifier, 'scenario': task.scenario_id}), flush=True)
        for identifier in identifiers:
            job = runner.wait(identifier)
            print(json.dumps({k: job.get(k) for k in ['id', 'scenario_id', 'state', 'export_status',
                                                      'authentication_required', 'scope_violation']}), flush=True)
    finally:
        runner.close(wait=True)


if __name__ == '__main__':
    main()
