#!/usr/bin/env python3
"""Launch the private voice pilot server. No H task starts before UI approval.

Run with an isolated Python containing the requirements listed in pilot/README.md.
Extracts pinned team source from this local Git clone; never merges teammate files.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE_REV = 'b59ef01'
SUPPORT_REV = 'bd3b2ca'
BROWSER_ENGINE_REV = '0ffda3f'
BROWSER_SUPPORT_REV = 'e46f9ee'


def extract(ref: str, part: str, destination: Path):
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', ref, '--', part], cwd=ROOT, text=True).splitlines()
    for name in paths:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(['git', 'show', f'{ref}:{name}'], cwd=ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-root', type=Path)
    parser.add_argument('--environment', choices=['minimal', 'rich'], default='minimal')
    parser.add_argument('--transport', choices=['desktop', 'browser'], default='desktop')
    parser.add_argument('--browser-access-dir', type=Path,
                        help='Private directory containing public-access.json and demo-access.json')
    parser.add_argument('--without-docs', action='store_true', help='Explicit no-document baseline for browser comparisons')
    parser.add_argument('--model-path', type=Path, default=Path.home() / 'Library/Application Support/HCompanionResearch/models/whisper-base-mlx')
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a non-privileged loopback port.')
    if args.transport == 'browser' and args.environment != 'rich':
        parser.error('The isolated browser currently supports only --environment rich.')
    if args.transport == 'browser' and not args.mock and args.browser_access_dir is None:
        parser.error('--browser-access-dir is required for the real isolated browser.')
    os.umask(0o077)
    # Never clean up H sessions belonging to the rest of the team.
    os.environ['HCS_AUTO_CLEANUP'] = '0'
    os.environ['HCS_GROUND_PLAN'] = '0'
    os.environ['HCS_MODEL'] = 'holo4-35b-a3b'
    default_name = 'voice-pilot-rich' if args.environment == 'rich' else 'voice-pilot'
    if args.transport == 'browser':
        default_name += '-browser'
    private = (args.private_root or Path.home() / 'Library/Application Support/HCompanionResearch' / default_name).resolve()
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any((parent / '.git').exists() for parent in (private, *private.parents)):
        raise SystemExit('Private pilot data must stay outside Git repositories.')
    # A second server must not rotate the running app token or share its state.
    import fcntl
    lock = (private / 'server.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A voice pilot already uses this private directory.') from None
    runtime = private / 'runtime'
    engine_rev = BROWSER_ENGINE_REV if args.transport == 'browser' else ENGINE_REV
    support_rev = BROWSER_SUPPORT_REV if args.transport == 'browser' else SUPPORT_REV
    for ref, part in [(engine_rev, 'agent'), (support_rev, 'backend')]:
        extract(ref, part, runtime / ref)
    sys.path[:0] = [str(ROOT), str(runtime / engine_rev / 'agent/src'), str(runtime / support_rev / 'backend/src')]
    from dotenv import dotenv_values
    from hcs_agent.backend import MockBackend
    from hcs_agent.knowledge import NoKnowledge
    from hcs_backend.store import Store
    from pilot.server import create_app
    from pilot.local_speech import LocalSpeech
    from pilot.environments import get_environment
    import uvicorn
    config = dotenv_values(ROOT / 'app/.env')
    key = config.get('HAI_API_KEY')
    if not args.mock and not key:
        raise SystemExit('HAI_API_KEY missing in app/.env.')
    token_path = private / 'pilot-token'
    token = secrets.token_urlsafe(32)
    token_path.write_text(token)
    os.chmod(token_path, 0o600)
    knowledge = None
    if args.transport == 'browser':
        from pilot.knowledge import LocalMarkdownKnowledge
        knowledge = LocalMarkdownKnowledge(private / 'knowledge', tenant_id='odoo-rich-v2.1', software='odoo')
        if not knowledge.list_documents():
            knowledge.upload('odoo-rich.md', (ROOT / 'docs/knowledge/odoo-rich.md').read_bytes())
    active_knowledge = knowledge if knowledge is not None and not args.without_docs else NoKnowledge()
    if args.mock:
        backend = MockBackend(knowledge=active_knowledge)
    elif args.transport == 'browser':
        from pilot.browser_backend import BrowserHBackend
        from pilot.browser_runtime import BrowserConfig, BrowserCredentials
        from pilot.runtime_config import browser_credentials
        origin = 'https://holo-demo.62.83.79.254.sslip.io'
        try:
            values = browser_credentials(args.browser_access_dir, expected_origin=origin)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        backend = BrowserHBackend(browser_config=BrowserConfig(origin=origin, start_path='/odoo/crm', width=1280, height=832),
                                  browser_credentials=BrowserCredentials(**values),
                                  model='holo4-35b-a3b', api_key=key, knowledge=active_knowledge)
    else:
        from pilot.desktop_backend import PilotHBackend
        backend = PilotHBackend(model='holo4-35b-a3b', api_key=key, knowledge=active_knowledge)

    console_credentials = None
    if args.transport == 'browser':
        console_path = private / 'company-credentials.json'
        if not console_path.exists():
            console_path.write_text(json.dumps({'username': 'support', 'password': secrets.token_urlsafe(32)}) + '\n')
        os.chmod(console_path, 0o600)
        console_secret = json.loads(console_path.read_text())
        console_credentials = (console_secret['username'], console_secret['password'])

    def export(report_path: Path, archive_dir: Path):
        env = os.environ.copy()
        env['HAI_API_KEY'] = key or ''
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/trace_export_h.py'), '--report', str(report_path), '--output', str(archive_dir)],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
        manifest = archive_dir / 'export.json'
        data = json.loads(manifest.read_text()) if manifest.is_file() else {}
        sessions = data.get('sessions', {})
        complete = result.returncode == 0 and bool(sessions) and all(item.get('archive_complete') is True for item in sessions.values())
        return {'archive_complete': complete, 'archive': str(archive_dir), 'manifest': data, 'ready_for_sft': False}

    store = Store(private / 'support.sqlite3')
    gladia_key = config.get('GLADIA_API_KEY')
    if gladia_key and not args.mock:
        from pilot.gladia_speech import GladiaSpeech
        transcriber = GladiaSpeech(gladia_key)
    else:
        transcriber = LocalSpeech(args.model_path)
    app = create_app(private_root=private, token=token, backend=backend, transcriber=transcriber,
                     exporter=export, store=store, model='holo4-35b-a3b',
                     scenarios_path=ROOT / 'docs/scenarios/odoo-scenarios.md', procedures_dir=ROOT / 'docs/scenarios',
                     environment=args.environment, engine_revision=engine_rev, support_revision=support_rev,
                     transport=args.transport, viewport={'width': 1280, 'height': 832} if args.transport == 'browser' else None,
                     knowledge=knowledge, knowledge_enabled=not args.without_docs and knowledge is not None,
                     console_credentials=console_credentials)
    (private / 'runtime.json').write_text(json.dumps({'engine_revision': engine_rev, 'support_revision': support_rev,
                                                   'desktop_adapter': getattr(backend, 'adapter_revision', None),
                                                   'transport': args.transport,
                                                   'image_policy': 'browser_viewport' if args.transport == 'browser' else 'full_screen',
                                                   'knowledge_enabled': not args.without_docs and knowledge is not None,
                                                   'simulated': args.mock, 'model': 'holo4-35b-a3b',
                                                   'environment': get_environment(args.environment),
                                                   'transcription_provider': transcriber.provider, 'port': args.port}, indent=2) + '\n')
    print(f'Voice pilot ready on 127.0.0.1:{args.port}; token file: {token_path}; simulated={args.mock}; transport={args.transport}', flush=True)
    if console_credentials:
        print(f'Company console: http://127.0.0.1:{args.port}/company ; credentials file: {console_path}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
