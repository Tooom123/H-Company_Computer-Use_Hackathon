#!/usr/bin/env python3
"""Start/reopen the private coach from Finder without attaching it to a terminal.

Only standard-library imports: a Finder launcher can use the system Python and
read the separately configured virtual environment. No credentials are copied.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / 'Library/Application Support/HCompanionResearch/human-cognition'
CONTROL_PORT = 8780
BACKEND_PORT = 8781
BUNDLE = 'com.exafunction.windsurf'
PROFILE = 'devin'


def configure_profile(profile):
    global PROFILE, PRIVATE, CONTROL_PORT, BACKEND_PORT
    PROFILE = profile
    name = 'main-vision-coach' if profile == 'hcompany-vision' else 'human-cognition'
    PRIVATE = Path.home() / 'Library/Application Support/HCompanionResearch' / name
    CONTROL_PORT, BACKEND_PORT = (8794, 8795) if profile == 'hcompany-vision' else (8780, 8781)


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def python_executable(private=None):
    private = private or PRIVATE
    configured = os.environ.get('HCS_PILOT_PYTHON') or read_json(private / 'launcher.json').get('python')
    # A stale temporary venv must not disable an otherwise healthy checkout.
    candidates = [configured, str(ROOT / '.venv/bin/python'), sys.executable]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            # Do not resolve the symlink: that would bypass the virtual environment.
            check = subprocess.run([candidate, '-c', 'import dotenv, uvicorn, AppKit, sounddevice'],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=15)
            if check.returncode == 0:
                return str(Path(candidate).absolute())
    raise RuntimeError('Python dependencies are unavailable. Run uv sync --all-packages or configure the private launcher.json.')


def control_status():
    request = urllib.request.Request(f'http://127.0.0.1:{CONTROL_PORT}/status', headers={'X-HCS-App': '1'})
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            data = json.load(response)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, urllib.error.HTTPError):
        return None


def port_busy(port):
    with socket.socket() as probe:
        # Match HTTPServer/uvicorn: a recently closed connection in TIME_WAIT is
        # not a live coach and must not prevent an immediate, explicit restart.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
            return False
        except OSError:
            return True


def owns_runtime(status, metadata):
    agent = (status or {}).get('agent') or {}
    vision = PROFILE == 'hcompany-vision'
    return (isinstance(agent, dict) and isinstance(agent.get('pid'), int) and agent['pid'] == metadata.get('pid')
            and metadata.get('software') == ('hcompany' if vision else 'cognition')
            and metadata.get('surface') == ('browser' if vision else 'devin-desktop')
            and metadata.get('native_bundle_id') == (None if vision else BUNDLE)
            and agent.get('observe_only') is True)


def ready(status):
    voice = (status or {}).get('voice') or {}
    return isinstance(voice, dict) and bool(voice.get('ptt_key'))


def start_runtime(python, private=None):
    private = private or PRIVATE
    metadata = lambda: read_json(private / 'runtime.json')
    status = control_status()
    if status is not None:
        if not owns_runtime(status, metadata()):
            raise RuntimeError(f'Port {CONTROL_PORT} belongs to a different coach. Close that runtime before reopening H Companion.')
        if ready(status):
            return False
        # A previous launcher may still be preparing the microphone/channel.
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            time.sleep(0.4)
            status = control_status()
            if owns_runtime(status, metadata()) and ready(status):
                return False
        raise RuntimeError('The existing coach is not ready. Inspect the private logs before retrying.')
    if port_busy(CONTROL_PORT) or port_busy(BACKEND_PORT):
        raise RuntimeError(f'Port {CONTROL_PORT} or {BACKEND_PORT} is occupied. No existing process was stopped.')
    command = [python, '-u', str(ROOT / 'scripts/run-h-company-human.py'),
               '--software', 'hcompany' if PROFILE == 'hcompany-vision' else 'cognition',
               '--input-language', 'fr-en']
    if PROFILE == 'hcompany-vision':
        command += ['--control-port', str(CONTROL_PORT), '--backend-port', str(BACKEND_PORT), '--key', 'alt_r']
    else:
        command += ['--native-devin']
    env_file = read_json(private / 'launcher.json').get('env_file')
    if env_file:
        source = Path(env_file).expanduser()
        if not source.is_file():
            raise RuntimeError('The configured private credentials file is missing. Check launcher.json.')
        command += ['--env-file', str(source.absolute())]
    command += ['--private-root', str(private)]
    stamp = time.strftime('%Y%m%d-%H%M%S')
    log_path = private / ('runtime-' + stamp + '.log')
    with log_path.open('ab') as log:
        proc = subprocess.Popen(command,
                                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('The coach could not start. Details are in the private runtime log: ' + str(log_path))
        status = control_status()
        if owns_runtime(status, metadata()) and status['agent']['pid'] == proc.pid and ready(status):
            return True
        time.sleep(0.4)
    # Leave the owned process intact: starting slowly is not permission to kill a task.
    raise RuntimeError('The coach is still starting. Wait a moment, then reopen H Companion.')


def start_desktop(python, private=None):
    private = private or PRIVATE
    config = read_json(private / 'launcher.json')
    electron = Path(config.get('electron') or ROOT / 'desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron').expanduser()
    if not electron.is_file():
        raise RuntimeError('Electron is unavailable. Run npm ci --prefix desktop first.')
    env = dict(os.environ)
    for key in ('ELECTRON_RUN_AS_NODE', 'HAI_API_KEY', 'GLADIA_API_KEY', 'ELEVENLABS_API_KEY',
                'ELEVEN', 'MISTRAL_API_KEY', 'HCS_INGEST_TOKEN'):
        env.pop(key, None)
    env.update(HCS_CONTROL_URL=f'http://127.0.0.1:{CONTROL_PORT}', HCS_BACKEND_URL=f'http://127.0.0.1:{BACKEND_PORT}',
               HCS_PILOT_KIND='hcompany-vision' if PROFILE == 'hcompany-vision' else 'devin-native', HCS_PILOT_PYTHON=python)
    command = [str(electron), str(ROOT / 'desktop')]
    if PROFILE == 'hcompany-vision':
        env.update(HCS_VISION_BUILTIN='1', HCS_VISION_WINDOW='native',
                   HCS_TRACKER_PYTHON=str(ROOT / 'desktop/tracker/.venv/bin/python'))
        command += ['--section=vision']
    with (private / 'desktop.log').open('ab') as log:
        proc = subprocess.Popen(command, cwd=ROOT / 'desktop', env=env,
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)
    # A second instance exits successfully after raising the already-running window.
    try:
        code = proc.wait(timeout=1)
        if code:
            raise RuntimeError('The desktop window could not open. Inspect the private desktop.log.')
    except subprocess.TimeoutExpired:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('devin', 'hcompany-vision'), default='devin')
    parser.add_argument('--backend-only', action='store_true', help='Start/reuse only the Devin coach, from its menu icon.')
    args = parser.parse_args()
    configure_profile(args.profile)
    if sys.platform != 'darwin':
        parser.error('This launcher is for H Companion on macOS.')
    os.umask(0o077)
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Serialize repeated Finder/tray clicks; never launch a second microphone listener.
    with (PRIVATE / 'launcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            python = python_executable()
            started = start_runtime(python)
            if not args.backend_only:
                start_desktop(python)
            print('H Companion ready. ' + ('Started.' if started else 'Already running.')
                  + (' Open H Companion from its menu-bar icon.' if not args.backend_only else ''))
            return 0
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            # RuntimeErrors are curated; do not expose external exceptions or subprocess output in UI.
            print(str(exc) if isinstance(exc, RuntimeError) else 'Launch failed. Inspect the private coaching logs.', file=sys.stderr)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
