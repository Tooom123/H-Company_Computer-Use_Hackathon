#!/usr/bin/env python3
"""Start the isolated H Platform coach V2, without stopping any existing coach.

The launcher uses the existing local Python/Electron installations. Credentials,
logs and recordings stay private; the new worktree supplies the code and UI.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'h-companion'
PRIVATE = Path.home() / 'Library/Application Support/HCompanionResearch/h-platform-coach-v2'
DEFAULT_PYTHON = '/private/tmp/hcompanion-matteo-pilot-venv/bin/python'
ENGINE = 'coach-v2'
SECRET_NAMES = {'HAI_API_KEY', 'GLADIA_API_KEY', 'ELEVENLABS_API_KEY', 'ELEVEN'}
SPEECH_NAMES = {'HCS_TTS_PROVIDER', 'HCS_TTS_VOICE', 'HCS_TTS_MODEL', 'HCS_TTS_MACOS_VOICE'}


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_json(path, value):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(value, indent=2) + '\n')
    pending.replace(path)


def control_status(port):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/status', headers={'X-HCS-App': '1'})
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            data = json.load(response)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, urllib.error.HTTPError):
        return None


def identity(status):
    status = status or {}
    agent = status.get('agent') or {}
    if not isinstance(agent, dict):
        agent = {}
    return status.get('engine') or agent.get('engine'), status.get('pid') or agent.get('pid')


def owns_runtime(status, metadata, port):
    engine, pid = identity(status)
    return (engine == ENGINE and isinstance(pid, int) and pid > 1
            and pid == metadata.get('pid') and metadata.get('engine') == ENGINE
            and metadata.get('control_port') == port and metadata.get('repository') == str(ROOT))


def port_busy(port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
            return False
        except OSError:
            return True


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def python_executable():
    candidate = os.environ.get('HCS_PYTHON', DEFAULT_PYTHON)
    path = Path(candidate).expanduser().absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError('Python is unavailable. Set HCS_PYTHON to the existing companion virtualenv Python.')
    # Preserve the virtualenv symlink: resolving it would select the base Python.
    check = subprocess.run([str(path), '-c', 'import dotenv, AppKit, sounddevice'],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15)
    if check.returncode:
        raise RuntimeError('The configured Python lacks coach dependencies. Set HCS_PYTHON to the companion virtualenv.')
    return str(path)


def runtime_environment(python, private, port, key):
    source = Path(os.environ.get('HCS_V2_ENV_SOURCE', str(SOURCE))).expanduser().absolute()
    research = PRIVATE.parent
    paths = [source / 'app/.env', source / 'agent/.env',
             research / 'human-cognition/speech.env', research / 'human-h-company/speech.env']
    # Capture the dotenv parser's output in a local pipe. It is never logged or
    # forwarded to Electron; external exceptions likewise never reveal content.
    loader = ('import json,sys; from dotenv import dotenv_values; values={}; '
              '[values.update({k:v for k,v in dotenv_values(p).items() if v}) for p in sys.argv[1:]]; '
              'print(json.dumps(values))')
    result = subprocess.run([python, '-c', loader, *map(str, paths)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=15)
    try:
        values = json.loads(result.stdout) if result.returncode == 0 else None
    except ValueError:
        values = None
    if not isinstance(values, dict):
        raise RuntimeError('The private environment could not be loaded. No values were printed.')
    env = dict(os.environ)
    for name in SECRET_NAMES | SPEECH_NAMES:
        if values.get(name):
            env.setdefault(name, values[name])
    if not env.get('HAI_API_KEY') or not env.get('GLADIA_API_KEY'):
        raise RuntimeError('HAI_API_KEY and GLADIA_API_KEY are required in the existing private environment.')
    env.pop('HCS_AX_NATIVE_BUNDLE_ID', None)
    env.update(PYTHONPATH=os.pathsep.join([str(ROOT / 'agent/src'), str(ROOT / 'backend/src'), str(ROOT)]),
               HCS_CONTROL_URL=f'http://127.0.0.1:{port}', HCS_CONTROL_PORT=str(port),
               HCS_RUNS_DIR=str(private / 'episodes'), HCS_PTT_KEY=key)
    # The shared transcriber otherwise defaults to French only. Preserve English
    # demo requests while still accepting French; narration stays English in the coach.
    env.setdefault('HCS_VOICE_LANGUAGE', 'fr-en')
    env.setdefault('HCS_TTS_PROVIDER', 'macos')
    env.setdefault('HCS_TTS_MACOS_VOICE', 'Samantha')
    return env


def start_runtime(python, private, port, key):
    metadata_path = private / 'launcher-runtime.json'
    status = control_status(port)
    if status is not None:
        if owns_runtime(status, read_json(metadata_path), port):
            return False
        raise RuntimeError(f'Port {port} belongs to a different runtime. No process was stopped.')
    if port_busy(port):
        raise RuntimeError(f'Port {port} is occupied. No process was stopped.')
    previous = read_json(metadata_path)
    if (previous.get('engine') == ENGINE and previous.get('repository') == str(ROOT)
            and previous.get('control_port') == port and process_alive(previous.get('pid'))):
        raise RuntimeError('The previous V2 process is still alive but not ready. Inspect its private log before retrying.')
    env = runtime_environment(python, private, port, key)
    log_path = private / ('runtime-' + time.strftime('%Y%m%d-%H%M%S') + '.log')
    with log_path.open('ab') as log:
        proc = subprocess.Popen([python, '-u', '-m', 'hcs_agent.coach_v2_runtime', '--port', str(port),
                                 '--runs-dir', str(private / 'episodes'), '--ptt-key', key],
                                cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    metadata = {'engine': ENGINE, 'pid': proc.pid, 'repository': str(ROOT), 'control_port': port,
                'runs_dir': str(private / 'episodes'), 'log': str(log_path), 'ptt_key': key}
    atomic_json(metadata_path, metadata)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('Coach V2 did not start. Inspect its private runtime log.')
        if owns_runtime(control_status(port), metadata, port):
            return True
        time.sleep(0.3)
    raise RuntimeError('Coach V2 is still starting. Inspect its private log, then rerun this launcher. No process was stopped.')


def stop_owned_runtime(private, port):
    status = control_status(port)
    if status is None:
        if port_busy(port):
            raise RuntimeError('The occupied port cannot be identified. No process was stopped.')
        print('Coach V2 is not running.')
        return
    metadata = read_json(private / 'launcher-runtime.json')
    if not owns_runtime(status, metadata, port):
        raise RuntimeError('Runtime ownership does not match this V2 launcher. No process was stopped.')
    os.kill(metadata['pid'], signal.SIGTERM)
    print('Stop requested for this V2 runtime only. Its private traces are preserved.')


def start_desktop(python, private, port, key):
    suffix = 'desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'
    configured = os.environ.get('HCS_ELECTRON')
    candidates = [Path(configured).expanduser()] if configured else [ROOT / suffix, SOURCE / suffix]
    electron = next((p.absolute() for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)
    if electron is None:
        raise RuntimeError('Electron is unavailable. Set HCS_ELECTRON to the existing Electron executable.')
    env = {k: v for k, v in os.environ.items() if k not in SECRET_NAMES | {'HCS_INGEST_TOKEN'}}
    env.pop('ELECTRON_RUN_AS_NODE', None)
    env.update(HCS_CONTROL_URL=f'http://127.0.0.1:{port}', HCS_PILOT_KIND=ENGINE,
               HCS_PILOT_PYTHON=python, HCS_PYTHON=python,
               HCS_RUNTIME_LAUNCHER=str(Path(__file__).resolve()),
               HCS_DESKTOP_USER_DATA=str(private / 'desktop-profile'),
               HCS_V2_PRIVATE_ROOT=str(private), HCS_V2_PORT=str(port), HCS_V2_PTT_KEY=key)
    with (private / 'desktop.log').open('ab') as log:
        proc = subprocess.Popen([str(electron), str(ROOT / 'desktop')], cwd=ROOT / 'desktop', env=env,
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)
    try:
        if proc.wait(timeout=1):
            raise RuntimeError('Coach V2 desktop could not open. Inspect its private desktop.log.')
    except subprocess.TimeoutExpired:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-only', action='store_true', help='Start/reuse the V2 runtime without opening Electron.')
    parser.add_argument('--stop-owned-runtime', action='store_true', help='Stop only the V2 PID verified by its status and metadata.')
    parser.add_argument('--private-root', type=Path, default=Path(os.environ.get('HCS_V2_PRIVATE_ROOT', PRIVATE)))
    parser.add_argument('--port', type=int, default=int(os.environ.get('HCS_V2_PORT', 8792)))
    parser.add_argument('--ptt-key', default=os.environ.get('HCS_V2_PTT_KEY', 'alt_r'))
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This desktop launcher requires macOS.')
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a local port between 1024 and 65535.')
    private = args.private_root.expanduser().resolve()
    if any((p / '.git').exists() for p in (private, *private.parents)):
        parser.error('Private recordings and logs must stay outside a Git checkout.')
    os.umask(0o077)
    try:
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (private / 'launcher.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.stop_owned_runtime:
                stop_owned_runtime(private, args.port)
                return 0
            python = python_executable()
            started = start_runtime(python, private, args.port, args.ptt_key)
            if not args.backend_only:
                start_desktop(python, private, args.port, args.ptt_key)
        print('H Platform coach V2 ready. ' + ('Started.' if started else 'Already running.'))
        print(f'Control: http://127.0.0.1:{args.port} · hold Right Option to speak.' if args.ptt_key == 'alt_r'
              else f'Control: http://127.0.0.1:{args.port} · talk shortcut: {args.ptt_key}')
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else 'Launch failed. Inspect the private Coach V2 logs.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
