#!/usr/bin/env python3
"""Publish only the seven public landing files on the existing Netcup Caddy instance.

No containers are recreated. An expected Caddy hash protects concurrent edits.
The complete existing configuration stays private on the server.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ('index.html', 'style.css', 'main.js', 'annotate.js', 'margin.js', 'billing.js', 'favicon.svg')

REMOTE = r"""
import base64, fcntl, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path
payload = json.load(sys.stdin)
names = ('index.html','style.css','main.js','annotate.js','margin.js','billing.js','favicon.svg')
assert set(payload['files']) == set(names), 'Unexpected public assets'
files = {name: base64.b64decode(payload['files'][name], validate=True) for name in names}
digest = hashlib.sha256(b''.join(name.encode()+b'\0'+files[name] for name in names)).hexdigest()
assert digest == payload['digest'], 'Release digest mismatch'
assert all(len(data) < 2_000_000 for data in files.values()), 'Unexpected asset size'
assert re.fullmatch('[a-f0-9]{64}', payload['expected_caddy_sha']), 'Invalid config hash'
container = 'dejabu-edge-caddy-1'
config = Path('/opt/dejabu/edge/Caddyfile')
private = Path('/opt/hcompanion/landing')
private.mkdir(parents=True, exist_ok=True, mode=0o700)
lock = (private/'deploy.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX)
original = config.read_bytes()
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(original) == payload['expected_caddy_sha'], 'Caddy changed; inspect it and retry with its current hash'
begin, end = b'# BEGIN HCOMPANION PUBLIC LANDING\n', b'# END HCOMPANION PUBLIC LANDING\n'
assert original.count(begin) == original.count(end) <= 1, 'Ambiguous deployment markers'
root = '/data/hcompanion/landing/releases/' + digest
block = ('''# BEGIN HCOMPANION PUBLIC LANDING
hcompanion.help {
    root * ROOT
    encode zstd gzip
    header X-Content-Type-Options nosniff
    header Referrer-Policy strict-origin-when-cross-origin
    file_server
}
www.hcompanion.help {
    redir https://hcompanion.help{uri} permanent
}
hcompanion.62.83.79.254.sslip.io {
    root * ROOT
    encode zstd gzip
    header X-Content-Type-Options nosniff
    header X-Robots-Tag "noindex, nofollow, noarchive"
    file_server
}
# END HCOMPANION PUBLIC LANDING
''').replace('ROOT', root).encode()
if begin in original:
    start = original.index(begin)
    finish = original.index(end, start) + len(end)
    candidate = original[:start] + block + original[finish:]
    preserved = candidate[:start] == original[:start] and candidate[start+len(block):] == original[finish:]
else:
    assert b'hcompanion.help' not in original and b'hcompanion.62.83.79.254.sslip.io' not in original, 'Unmanaged domain exists'
    candidate = original + (b'' if original.endswith(b'\n') else b'\n') + block
    preserved = candidate.startswith(original)
assert preserved, 'Existing configuration would change'

def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    if result.returncode:
        (private/'last-command-error.log').write_text(result.stdout + result.stderr)
        (private/'last-command-error.log').chmod(0o600)
        raise RuntimeError('Server command failed; inspect private last-command-error.log')
    return result.stdout

before_containers = run(['docker','ps','--format','{{.ID}} {{.Names}}']).splitlines()
urls = ('https://app-bruxelles.deja-bu.com','https://caisse-bruxelles.deja-bu.com','https://holo-demo.62.83.79.254.sslip.io/web/login')
def health():
    return {url:run(['curl','--max-time','10','-sS','-o','/dev/null','-w','%{http_code}',url]) for url in urls}
before_health = health()
public = Path('/var/lib/docker/volumes/dejabu-edge_data/_data/hcompanion/landing')
release = public/'releases'/digest
release.mkdir(parents=True, exist_ok=True, mode=0o755)
for parent in (public.parent, public, public/'releases', release):
    parent.chmod(0o755)
for name, data in files.items():
    path = release/name
    if path.exists():
        assert path.read_bytes() == data, 'Existing immutable release differs'
    else:
        path.write_bytes(data)
        path.chmod(0o644)
assert set(p.name for p in release.iterdir()) == set(names), 'Unexpected file in public release'
stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
backup = private/('Caddyfile.'+stamp+'.before')
backup.write_bytes(original)
backup.chmod(0o600)
staged = private/('Caddyfile.'+digest+'.candidate')
staged.write_bytes(candidate)
staged.chmod(0o600)
inside = '/tmp/hcompanion-'+digest+'.Caddyfile'
run(['docker','cp',str(staged),container+':'+inside])
run(['docker','exec',container,'caddy','validate','--config',inside,'--adapter','caddyfile'])
assert config.read_bytes() == original, 'Caddy changed during validation; no config was written'
def write_in_place(data):
    # Preserve the inode: Caddy mounts this exact host file read-only.
    with config.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
write_in_place(candidate)
try:
    run(['docker','exec',container,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
except Exception:
    if config.read_bytes() == candidate:
        write_in_place(original)
        run(['docker','exec',container,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
    raise
current = public/'current'
pending = public/('.current-'+digest)
if pending.is_symlink():
    pending.unlink()
pending.symlink_to('releases/'+digest)
pending.replace(current)
after_containers = run(['docker','ps','--format','{{.ID}} {{.Names}}']).splitlines()
after_health = health()
report = {'release_sha256':digest,'caddy_sha256':sha(candidate),'existing_config_preserved':preserved,
          'container_ids_unchanged':sorted(before_containers)==sorted(after_containers),
          'before_health':before_health,'after_health':after_health,'health_unchanged':before_health==after_health,
          'public_files':list(names),'preview':'https://hcompanion.62.83.79.254.sslip.io/',
          'domain':'https://hcompanion.help/','certificate_pending_verification':True}
(private/('release-'+digest+'.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-config', type=Path, required=True)
    parser.add_argument('--host', default='netcup-holo')
    parser.add_argument('--expect-caddy-sha', required=True)
    parser.add_argument('--apply', action='store_true', help='Publish; otherwise print the allowlisted release manifest.')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{64}', args.expect_caddy_sha):
        parser.error('Expected Caddy SHA-256 must be 64 lowercase hex characters.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.host):
        parser.error('Use a configured SSH host alias.')
    files = {}
    for name in ASSETS:
        source = ROOT/'landing'/name
        if source.is_symlink() or not source.is_file():
            parser.error('Missing or linked public asset: ' + name)
        files[name] = source.read_bytes()
    digest = hashlib.sha256(b''.join(name.encode()+b'\0'+files[name] for name in ASSETS)).hexdigest()
    if not args.apply:
        print(json.dumps({'release_sha256':digest,'public_files':list(files),'bytes':sum(map(len,files.values()))},indent=2))
        return
    payload = {'files':{name:base64.b64encode(data).decode() for name,data in files.items()},
               'digest':digest,'expected_caddy_sha':args.expect_caddy_sha}
    subprocess.run(['ssh','-F',str(args.ssh_config),'-o','BatchMode=yes','-o','ConnectTimeout=8',args.host,
                    'python3 -c '+shlex.quote(REMOTE)], input=json.dumps(payload), text=True, check=True)


if __name__ == '__main__':
    main()
