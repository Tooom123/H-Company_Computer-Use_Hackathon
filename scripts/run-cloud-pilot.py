#!/usr/bin/env python3
"""Launch the local company console. Cloud campaigns require explicit API approval."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE_REV = '6f166d1'
SUPPORT_REV = '8066ddf'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-root', type=Path, default=Path.home() / 'Library/Application Support/HCompanionResearch/cloud-pilot')
    parser.add_argument('--port', type=int, default=8771)
    parser.add_argument('--max-parallel', type=int, default=2)
    parser.add_argument('--history', type=Path, action='append', default=[])
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not 1 <= args.max_parallel <= 10:
        parser.error('Choose a local port and between 1 and 10 parallel jobs.')
    os.umask(0o077)
    private = args.private_root.expanduser().resolve()
    if any((p / '.git').exists() for p in (private, *private.parents)):
        parser.error('Private recordings must stay outside Git.')
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    private.chmod(0o700)
    lock = (private / 'server.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A cloud pilot already uses this directory.') from None
    helper = module('voice_pilot_launcher', ROOT / 'scripts/run-voice-pilot.py')
    for ref, part in ((ENGINE_REV, 'agent'), (SUPPORT_REV, 'backend')):
        helper.extract(ref, part, private / 'runtime' / ref)
    sys.path[:0] = [str(ROOT), str(private / 'runtime' / ENGINE_REV / 'agent/src'),
                   str(private / 'runtime' / SUPPORT_REV / 'backend/src')]
    from dotenv import dotenv_values
    from hai_agents import Client
    from pilot.cloud_runtime import CloudCampaignRunner
    from pilot.cloud_server import create_cloud_app
    from pilot.knowledge import LocalMarkdownKnowledge
    import uvicorn
    key = dotenv_values(ROOT / 'app/.env').get('HAI_API_KEY')
    if not key:
        raise SystemExit('HAI_API_KEY is missing from app/.env.')
    token = secrets.token_urlsafe(32)
    (private / 'pilot-token').write_text(token)
    credentials_path = private / 'company-credentials.json'
    if not credentials_path.exists():
        credentials_path.write_text(json.dumps({'username': 'support', 'password': secrets.token_urlsafe(32)}) + '\n')
    credentials = json.loads(credentials_path.read_text())
    client = Client(api_key=key)
    archive = module('h_cloud_trace_export', ROOT / 'scripts/trace_export_h.py')
    resource_client = archive.CloudClient(key)

    def export(session_id, directory):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return archive.archive_session(resource_client, session_id, directory)

    runner = CloudCampaignRunner(private, client, resource_client=client,
                                 exporter=export, max_parallel=args.max_parallel)
    knowledge = LocalMarkdownKnowledge(private / 'knowledge', tenant_id='h-company-cloud', software='h-company')
    account_path = private / 'account.json'
    account = json.loads(account_path.read_text()) if account_path.exists() else {}
    revisions = {'engine_revision': ENGINE_REV, 'support_revision': SUPPORT_REV}
    historical = [{'id': f'odoo-{i+1}', 'label': f'Odoo · série locale {i+1}',
                   'root': path, 'software': 'odoo'} for i, path in enumerate(args.history)]
    app = create_cloud_app(private_root=private, token=token, runner=runner, knowledge=knowledge,
                           username=credentials['username'], password=credentials['password'],
                           historical_sources=historical, account_configuration=account, revisions=revisions)
    (private / 'runtime.json').write_text(json.dumps({**revisions, 'port': args.port,
        'transport': 'h_cloud_browser', 'model': 'holo4-35b-a3b', 'simulated': False,
        'purpose': 'capability_test', 'company_url': f'http://127.0.0.1:{args.port}/company/live'}, indent=2) + '\n')
    print(f'Control tower: http://127.0.0.1:{args.port}/company/live', flush=True)
    print(f'Private credentials file: {credentials_path}', flush=True)
    try:
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
    finally:
        runner.close(wait=True)


if __name__ == '__main__':
    main()
