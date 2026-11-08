#!/usr/bin/env python3
"""Release the public landing through an SSH key restricted to this receiver.

The SSH account can invoke only this root-owned receiver, through a fixed sudo
command. It cannot run a shell, write Caddy configuration, restart containers,
or publish files outside ASSETS.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ASSETS = ('index.html', 'style.css', 'main.js', 'annotate.js', 'margin.js', 'billing.js', 'favicon.svg')
PUBLIC = Path('/var/lib/docker/volumes/dejabu-edge_data/_data/hcompanion/landing')
MAX_ASSET = 2_000_000
MAX_PAYLOAD = 20_000_000


def digest_files(files):
    return hashlib.sha256(b''.join(name.encode() + b'\0' + files[name] for name in ASSETS)).hexdigest()


def package(source, revision):
    files = {}
    for name in ASSETS:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or linked public asset: ' + name)
        files[name] = path.read_bytes()
    payload = {'version': 1, 'revision': revision, 'digest': digest_files(files),
               'files': {name: base64.b64encode(data).decode() for name, data in files.items()}}
    validate(payload)
    return payload


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != {'version', 'revision', 'digest', 'files'}:
        raise ValueError('Invalid release fields')
    if type(payload['version']) is not int or payload['version'] != 1:
        raise ValueError('Unsupported release version')
    if not isinstance(payload['revision'], str) or not re.fullmatch('[a-f0-9]{40}', payload['revision']):
        raise ValueError('Invalid commit')
    if not isinstance(payload['digest'], str) or not re.fullmatch('[a-f0-9]{64}', payload['digest']):
        raise ValueError('Invalid digest')
    if not isinstance(payload['files'], dict) or set(payload['files']) != set(ASSETS):
        raise ValueError('Unexpected public assets')
    files = {}
    for name, encoded in payload['files'].items():
        if not isinstance(encoded, str) or len(encoded) > 4 * MAX_ASSET // 3 + 4:
            raise ValueError('Unexpected asset size')
        data = base64.b64decode(encoded, validate=True)
        if len(data) > MAX_ASSET:
            raise ValueError('Unexpected asset size')
        files[name] = data
    if digest_files(files) != payload['digest']:
        raise ValueError('Release digest mismatch')
    return files


def receive(payload, root=PUBLIC):
    files = validate(payload)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Public release root is unavailable')
    releases = root / 'releases'
    if releases.is_symlink() or not releases.is_dir():
        raise ValueError('Release directory is unavailable')
    with (root / '.deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = root / 'current'
        if not current.is_symlink() or not re.fullmatch(r'releases/[a-f0-9]{64}', os.readlink(current)):
            raise ValueError('Current release is not a managed link')
        previous = os.readlink(current)
        release = releases / payload['digest']
        if release.exists() or release.is_symlink():
            if release.is_symlink() or not release.is_dir() or set(p.name for p in release.iterdir()) != set(ASSETS):
                raise ValueError('Existing release is not an immutable asset directory')
            for name, data in files.items():
                path = release / name
                if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
                    raise ValueError('Existing immutable release differs')
        else:
            staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=releases))
            try:
                staging.chmod(0o755)
                for name, data in files.items():
                    path = staging / name
                    with path.open('xb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    path.chmod(0o644)
                staging.rename(release)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        pending = root / ('.current-' + uuid.uuid4().hex)
        try:
            pending.symlink_to('releases/' + payload['digest'])
            pending.replace(current)
        finally:
            if pending.is_symlink():
                pending.unlink()
        return {'release_sha256': payload['digest'], 'git_revision': payload['revision'],
                'previous_release': previous, 'files': list(ASSETS)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receive', action='store_true')
    parser.add_argument('--host', default='62.83.79.254')
    parser.add_argument('--user', default='hcompanion-deploy')
    parser.add_argument('--identity', type=Path)
    parser.add_argument('--known-hosts', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.receive:
        if os.geteuid() != 0:
            raise SystemExit('Use the installed restricted deployment command')
        raw = sys.stdin.buffer.read(MAX_PAYLOAD + 1)
        if len(raw) > MAX_PAYLOAD:
            raise SystemExit('Release exceeds the payload limit')
        print(json.dumps(receive(json.loads(raw))))
        return
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    payload = package(root / 'landing', revision)
    if not args.verify_only:
        if not args.identity or not args.known_hosts:
            parser.error('--identity and --known-hosts are required')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', args.host) or not re.fullmatch(r'[a-z][a-z0-9_-]*', args.user):
            parser.error('Invalid SSH destination')
        # OpenSSH parses -o values as config text, including spaces in the Mac's Application Support path.
        known_hosts = str(args.known_hosts).replace('\\', '\\\\').replace('"', '\\"')
        subprocess.run(['ssh', '-F', '/dev/null', '-i', str(args.identity), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                        '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile="' + known_hosts + '"',
                        '-o', 'ConnectTimeout=10', args.user + '@' + args.host, 'deploy'],
                       input=json.dumps(payload), text=True, check=True, timeout=90)
    # Check every published byte with normal TLS validation; redirects cannot leak SSH credentials.
    from urllib.request import urlopen
    for name in ASSETS:
        with urlopen('https://hcompanion.help/' + name, timeout=20) as response:
            actual = response.read(MAX_ASSET + 1)
        if actual != base64.b64decode(payload['files'][name]):
            raise SystemExit('Published asset differs: ' + name)
    print(json.dumps({'https_verified': True, 'release_sha256': payload['digest'], 'files': len(ASSETS)}))


if __name__ == '__main__':
    main()
