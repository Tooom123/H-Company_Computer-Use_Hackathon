#!/usr/bin/env python3
"""Latest team voice runtime for private, observation-only H or Devin coaching."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]


def atomic(path, value):
    temporary = path.with_suffix('.pending.json')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--software', choices=('hcompany', 'cognition'), default='hcompany')
    parser.add_argument('--native-devin', action='store_true',
                        help='Read the focused Devin Desktop accessibility tree instead of a browser tab.')
    parser.add_argument('--private-root', type=Path)
    parser.add_argument('--control-port', type=int, default=8780)
    parser.add_argument('--backend-port', type=int, default=8781)
    parser.add_argument('--key', default='ctrl+shift+h')
    parser.add_argument('--input-language', choices=('en', 'fr'), default='fr',
                        help='Language spoken by the human; companion responses stay in English.')
    args = parser.parse_args()
    if args.native_devin and args.software != 'cognition':
        parser.error('--native-devin requires --software cognition.')
    if args.control_port == args.backend_port or not all(1024 <= p <= 65535 for p in (args.control_port, args.backend_port)):
        parser.error('Choose two distinct local ports.')
    for port in (args.control_port, args.backend_port):
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                parser.error(f'Port {port} is already in use. Finish and stop the existing coaching runtime first.')
    private_name = 'human-cognition' if args.software == 'cognition' else 'human-h-company'
    private = (args.private_root or Path.home() / 'Library/Application Support/HCompanionResearch' / private_name).expanduser().resolve()
    if any((p / '.git').exists() for p in (private, *private.parents)):
        parser.error('Human recordings must stay outside Git.')
    os.umask(0o077)
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (private / 'server.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A human coaching runtime already owns this directory.') from None
    sys.path[:0] = [str(ROOT), str(ROOT/'agent/src'), str(ROOT/'backend/src')]
    from dotenv import dotenv_values
    for source in (ROOT/'app/.env', ROOT/'agent/.env'):
        for name, value in dotenv_values(source).items():
            if name in {'HAI_API_KEY', 'GLADIA_API_KEY', 'ELEVENLABS_API_KEY', 'ELEVEN'} and value:
                os.environ.setdefault(name, value)
    # Provider credentials belong outside the checkout, even when .env is ignored.
    speech_values = dict(dotenv_values(private.parent/'human-h-company/speech.env'))
    speech_values.update(dotenv_values(private/'speech.env'))
    for name, value in speech_values.items():
        if name in {'ELEVENLABS_API_KEY', 'ELEVEN', 'HCS_TTS_PROVIDER', 'HCS_TTS_VOICE',
                    'HCS_TTS_MODEL', 'HCS_TTS_MACOS_VOICE'} and value:
            os.environ.setdefault(name, value)
    if not all(os.environ.get(name) for name in ('HAI_API_KEY', 'GLADIA_API_KEY')):
        raise SystemExit('HAI_API_KEY and GLADIA_API_KEY are required in the private environment.')
    credentials_path = private/'credentials.json'
    if not credentials_path.exists():
        atomic(credentials_path, {'username':'support', 'password':secrets.token_urlsafe(32), 'ingest_token':secrets.token_urlsafe(32)})
    credentials = json.loads(credentials_path.read_text())
    runs = private/'episodes'
    runs.mkdir(exist_ok=True, mode=0o700)
    # These must be set before importing cli.py, whose defaults are import-time.
    os.environ.update(HCS_AUTONOMY='0', HCS_GUIDE_OBSERVE_ONLY='1', HCS_AUTO_CLEANUP='0',
        HCS_MODEL='holo4-35b-a3b', HCS_CONTROL_PORT=str(args.control_port),
        HCS_BACKEND_URL=f'http://127.0.0.1:{args.backend_port}', HCS_INGEST_TOKEN=credentials['ingest_token'],
        HCS_SUPPORT_USER=private_name, HCS_SUPPORT_EVENTS='1', HCS_PTT_KEY=args.key,
        HCS_RUNS_DIR=str(runs), HCS_VOICE_LANGUAGE=args.input_language)
    if args.native_devin:
        os.environ['HCS_AX_NATIVE_BUNDLE_ID'] = 'com.exafunction.windsurf'
    else:
        os.environ.pop('HCS_AX_NATIVE_BUNDLE_ID', None)
    # This Mac pilot can speak without an external TTS account. Keep an explicit
    # provider override (and HCS_TTS=0) available to the operator.
    os.environ.setdefault('HCS_TTS_PROVIDER', 'macos' if sys.platform == 'darwin' else 'auto')
    os.environ.setdefault('HCS_TTS_MACOS_VOICE', 'Samantha')
    from hcs_backend.app import create_app
    from hcs_backend.config import Settings
    import uvicorn
    settings = Settings(db_path=private/'backend.sqlite3', contracts_dir=ROOT/'contracts',
        port=args.backend_port, ingest_token=credentials['ingest_token'],
        dashboard_user=credentials['username'], dashboard_password=credentials['password'],
        fix_auto=False, fix_provider='mock')
    support = create_app(settings=settings, start_poller=False)
    server = uvicorn.Server(uvicorn.Config(support, host='127.0.0.1', port=args.backend_port, log_level='warning'))
    threading.Thread(target=server.run, name='human-support', daemon=True).start()
    from hcs_agent import cli
    from pilot.knowledge import LocalMarkdownKnowledge
    docs = private/'knowledge' if args.software == 'cognition' else private.parent/'cloud-pilot/knowledge'
    if docs.is_dir() or args.software == 'cognition':
        knowledge = LocalMarkdownKnowledge(docs,
            tenant_id='cognition-human' if args.software == 'cognition' else 'h-company-cloud',
            software='cognition' if args.software == 'cognition' else 'h-company')
        if args.software == 'cognition':
            source = ROOT/'agent/src/hcs_agent/data/cognition-guide-knowledge.md'
            knowledge.upload(source.name, source.read_text())
        original_backend = cli.make_backend
        def with_knowledge(mock=False):
            backend = original_backend(mock)
            backend.knowledge = knowledge
            return backend
        cli.make_backend = with_knowledge
        document_count = len(knowledge.list_documents())
    else:
        document_count = 0
    spec = importlib.util.spec_from_file_location('human_h_trace_export', ROOT/'scripts/trace_export_h.py')
    exporter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = exporter
    spec.loader.exec_module(exporter)
    client = exporter.CloudClient(os.environ['HAI_API_KEY'])

    def archive_finished(directory, report):
        """Only IDs recorded by this intervention; no account-wide lookup/cleanup."""
        identifiers = report.get('h_session_ids') or []
        meta_path = directory/'episode.json'
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        statuses = []
        for identifier in dict.fromkeys(identifiers):
            if not isinstance(identifier, str) or not identifier or any(c not in '0123456789abcdefABCDEF-' for c in identifier):
                statuses.append({'status':'invalid_owned_session_reference'})
                continue
            try:
                destination = directory/'archive'
                destination.mkdir(exist_ok=True, mode=0o700)
                manifest = exporter.archive_session(client, identifier, destination)
                statuses.append({'session_id':identifier, 'complete':manifest.get('archive_complete') is True})
            except Exception as exc:
                statuses.append({'session_id':identifier, 'complete':False, 'error_class':type(exc).__name__})
        atomic(directory/'archive-status.json', {'sessions':statuses, 'no_h_session':not identifiers})
        # The report is complete before this hook; preserve journal metadata.
        meta.update(export_status=('complete' if statuses and all(s.get('complete') for s in statuses)
                                   else 'unavailable' if not statuses else 'partial'))
        atomic(meta_path, meta)

    cli._RUN_FINISHED_HOOK = archive_finished
    revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    atomic(private/'runtime.json', {'git_revision':revision, 'pid':os.getpid(), 'model':'holo4-35b-a3b',
        'mode':'guide', 'human_present':True, 'observe_only':True, 'control_port':args.control_port,
        'backend_port':args.backend_port, 'knowledge_documents':document_count, 'voice':'gladia',
        'raw_microphone_audio_retained':False, 'software':args.software, 'response_language':'en',
        'input_language':args.input_language,
        'surface':'devin-desktop' if args.native_devin else 'browser',
        'native_bundle_id':os.environ.get('HCS_AX_NATIVE_BUNDLE_ID')})
    print(f'Human coaching control: http://127.0.0.1:{args.control_port}', flush=True)
    print(f'Support dashboard: http://127.0.0.1:{args.backend_port}/dashboard', flush=True)
    print(f'Private recordings: {private}; {args.software} documentation: {document_count} documents.', flush=True)
    sys.argv = ['hcs-agent','talk','--software',args.software,'--key',args.key,'--runs-dir',str(runs)]
    try:
        return cli.main()
    finally:
        server.should_exit = True


if __name__ == '__main__':
    main()
