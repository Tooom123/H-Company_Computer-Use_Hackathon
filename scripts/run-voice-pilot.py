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
ENGINE_REV = '343e393'
SUPPORT_REV = 'bd3b2ca'


def extract(ref: str, part: str, destination: Path):
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', ref, '--', part], cwd=ROOT, text=True).splitlines()
    for name in paths:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(['git', 'show', f'{ref}:{name}'], cwd=ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-root', type=Path, default=Path.home() / 'Library/Application Support/HCompanionResearch/voice-pilot')
    parser.add_argument('--model-path', type=Path, default=Path.home() / 'Library/Application Support/HCompanionResearch/models/whisper-base-mlx')
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--port', type=int, choices=[8767], default=8767)
    args = parser.parse_args()
    os.umask(0o077)
    # Never clean up H sessions belonging to the rest of the team.
    os.environ['HCS_AUTO_CLEANUP'] = '0'
    os.environ['HCS_GROUND_PLAN'] = '0'
    os.environ['HCS_MODEL'] = 'holo4-35b-a3b'
    private = args.private_root.resolve()
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
    for ref, part in [(ENGINE_REV, 'agent'), (SUPPORT_REV, 'backend')]:
        extract(ref, part, runtime)
    sys.path[:0] = [str(ROOT), str(runtime / 'agent/src'), str(runtime / 'backend/src')]
    from dotenv import dotenv_values
    from hcs_agent.backend import HBackend, MockBackend
    from hcs_agent.knowledge import NoKnowledge
    from hcs_backend.store import Store
    from pilot.server import create_app
    from pilot.local_speech import LocalSpeech
    import uvicorn
    config = dotenv_values(ROOT / 'app/.env')
    key = config.get('HAI_API_KEY')
    if not args.mock and not key:
        raise SystemExit('HAI_API_KEY missing in app/.env.')
    token_path = private / 'pilot-token'
    token = secrets.token_urlsafe(32)
    token_path.write_text(token)
    os.chmod(token_path, 0o600)
    backend = MockBackend() if args.mock else HBackend(model='holo4-35b-a3b', api_key=key, knowledge=NoKnowledge())

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
                     scenarios_path=ROOT / 'docs/scenarios/odoo-scenarios.md', procedures_dir=ROOT / 'docs/scenarios')
    (private / 'runtime.json').write_text(json.dumps({'engine_revision': ENGINE_REV, 'support_revision': SUPPORT_REV,
                                                   'simulated': args.mock, 'model': 'holo4-35b-a3b',
                                                   'transcription_provider': transcriber.provider, 'port': args.port}, indent=2) + '\n')
    print(f'Voice pilot ready on 127.0.0.1:{args.port}; token file: {token_path}; simulated={args.mock}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
