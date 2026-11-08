#!/usr/bin/env python3
"""Start/reopen the private Devin coach from Finder without attaching it to a terminal.

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


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def python_executable(private=PRIVATE):
    configured = os.environ.get('HCS_PILOT_PYTHON') or read_json(private / 'launcher.json').get('python')
    candidates = [configured] if configured else [str(ROOT / '.venv/bin/python'), sys.executable]
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
    request = urllib.request.Request('http://127.0.0.1:8780/status', headers={'X-HCS-App': '1'})
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
    return (isinstance(agent, dict) and isinstance(agent.get('pid'), int) and agent['pid'] == metadata.get('pid')
            and metadata.get('software') == 'cognition'
            and metadata.get('surface') == 'devin-desktop'
            and metadata.get('native_bundle_id') == BUNDLE
            and agent.get('observe_only') is True)


def ready(status):
    voice = (status or {}).get('voice') or {}
    return isinstance(voice, dict) and bool(voice.get('ptt_key'))


def start_runtime(python, private=PRIVATE):
    metadata = lambda: read_json(private / 'runtime.json')
    status = control_status()
    if status is not None:
        if not owns_runtime(status, metadata()):
            raise RuntimeError('Port 8780 belongs to a different coach. Close that runtime before starting Devin.')
        if ready(status):
            return False
        # A previous launcher may still be preparing the microphone/channel.
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            time.sleep(0.4)
            status = control_status()
            if owns_runtime(status, metadata()) and ready(status):
                return False
        raise RuntimeError('The existing Devin coach is not ready. Inspect the private logs before retrying.')
    if port_busy(CONTROL_PORT) or port_busy(BACKEND_PORT):
        raise RuntimeError('Port 8780 or 8781 is occupied. No existing process was stopped.')
    stamp = time.strftime('%Y%m%d-%H%M%S')
    log_path = private / ('runtime-' + stamp + '.log')
    with log_path.open('ab') as log:
        proc = subprocess.Popen([python, '-u', str(ROOT / 'scripts/run-h-company-human.py'),
                                 '--software', 'cognition', '--native-devin', '--input-language', 'fr-en',
                                 '--private-root', str(private)],
                                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('The Devin coach could not start. Details are in the private human-cognition runtime log.')
        status = control_status()
        if owns_runtime(status, metadata()) and status['agent']['pid'] == proc.pid and ready(status):
            return True
        time.sleep(0.4)
    # Leave the owned process intact: starting slowly is not permission to kill a task.
    raise RuntimeError('The Devin coach is still starting. Wait a moment, then use Start Devin coach again.')


def start_desktop(python, private=PRIVATE):
    electron = ROOT / 'desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'
    if not electron.is_file():
        raise RuntimeError('Electron is unavailable. Run npm ci --prefix desktop first.')
    env = dict(os.environ)
    env.pop('ELECTRON_RUN_AS_NODE', None)
    env.update(HCS_CONTROL_URL='http://127.0.0.1:8780', HCS_BACKEND_URL='http://127.0.0.1:8781',
               HCS_PILOT_KIND='devin-native', HCS_PILOT_PYTHON=python)
    with (private / 'desktop.log').open('ab') as log:
        proc = subprocess.Popen([str(electron), str(ROOT / 'desktop')], cwd=ROOT / 'desktop', env=env,
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
    parser.add_argument('--backend-only', action='store_true', help='Start/reuse only the Devin coach, from its menu icon.')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This launcher is for Devin Desktop on macOS.')
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
            print('Devin coach ready. ' + ('Started.' if started else 'Already running.')
                  + (' Open H Companion from its menu-bar icon.' if not args.backend_only else ''))
            return 0
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            # RuntimeErrors are curated; do not expose external exceptions or subprocess output in UI.
            print(str(exc) if isinstance(exc, RuntimeError) else 'Launch failed. Inspect the private human-cognition logs.', file=sys.stderr)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
