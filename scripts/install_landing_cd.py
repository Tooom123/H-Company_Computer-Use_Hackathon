#!/usr/bin/env python3
"""One-time installation of the restricted homepage deploy account on Netcup.

Run with the existing private operator SSH config. No operator key is uploaded
to GitHub. The CI key has a forced command and cannot request a terminal or tunnel.
"""
import argparse
import base64
import json
from pathlib import Path
import re
import shlex
import subprocess

REMOTE = r'''
import base64, hashlib, json, os, pwd, re, subprocess, sys, time
from pathlib import Path
p=json.load(sys.stdin)
assert re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [A-Za-z0-9._-]+)?',p['public_key'])
assert re.fullmatch('[a-f0-9]{64}',p['expected_caddy_sha'])
source=base64.b64decode(p['receiver'],validate=True)
compile(source,'receiver.py','exec')
def run(argv):
    r=subprocess.run(argv,capture_output=True,text=True,timeout=30)
    if r.returncode:raise RuntimeError('Setup command failed: '+argv[0])
    return r.stdout
config=Path('/opt/dejabu/edge/Caddyfile')
original=config.read_bytes()
assert hashlib.sha256(original).hexdigest()==p['expected_caddy_sha'],'Caddy changed'
begin,end=b'# BEGIN HCOMPANION PUBLIC LANDING\n',b'# END HCOMPANION PUBLIC LANDING\n'
assert original.count(begin)==original.count(end)==1
start=original.index(begin);finish=original.index(end,start)+len(end)
block=original[start:finish]
candidate_block,count=re.subn(rb'root \* /data/hcompanion/landing/(?:releases/[a-f0-9]{64}|current)',
    b'root * /data/hcompanion/landing/current',block)
assert count==2,'Unexpected landing routes'
candidate=original[:start]+candidate_block+original[finish:]
public=Path('/var/lib/docker/volumes/dejabu-edge_data/_data/hcompanion/landing')
assert (public/'current').is_symlink()
assert re.fullmatch(r'releases/[a-f0-9]{64}',os.readlink(public/'current'))
user='hcompanion-deploy'
home=Path('/var/lib/hcompanion-deploy')
try:
    account=pwd.getpwnam(user)
    assert account.pw_dir==str(home) and account.pw_uid!=0,'Unexpected deploy identity'
except KeyError:
    run(['useradd','--system','--home-dir',str(home),'--shell','/bin/sh',user])
account=pwd.getpwnam(user)
home.mkdir(exist_ok=True,mode=0o755);os.chown(home,0,0);home.chmod(0o755)
ssh=home/'.ssh';ssh.mkdir(exist_ok=True,mode=0o750);os.chown(ssh,0,account.pw_gid);ssh.chmod(0o750)
directory=Path('/opt/hcompanion/landing-cd')
directory.mkdir(parents=True,exist_ok=True,mode=0o755)
directory.chmod(0o755)
receiver=directory/'receiver.py'
pending=directory/'receiver.pending.py';pending.write_bytes(source);pending.chmod(0o644);pending.replace(receiver)
sudo_line=user+' ALL=(root) NOPASSWD: /usr/bin/python3 -I /opt/hcompanion/landing-cd/receiver.py --receive\n'
sudo_tmp=directory/'sudoers.pending';sudo_tmp.write_text(sudo_line);sudo_tmp.chmod(0o440)
run(['visudo','-cf',str(sudo_tmp)])
sudo_path=Path('/etc/sudoers.d/hcompanion-landing')
if sudo_path.exists():assert sudo_path.read_text()==sudo_line,'Unexpected sudo policy'
sudo_path.write_text(sudo_line);sudo_path.chmod(0o440)
command='if [ "$SSH_ORIGINAL_COMMAND" = deploy ]; then exec /usr/bin/sudo -n /usr/bin/python3 -I /opt/hcompanion/landing-cd/receiver.py --receive; else exit 1; fi'
entry='restrict,command="'+command.replace('"','\\"')+'" '+p['public_key']+'\n'
authorized=ssh/'authorized_keys'
if authorized.exists():assert authorized.read_text()==entry,'Deploy key already configured; rotate explicitly'
authorized.write_text(entry);os.chown(authorized,0,account.pw_gid);authorized.chmod(0o640)
container='dejabu-edge-caddy-1'
before=run(['docker','ps','--format','{{.ID}} {{.Names}}']).splitlines()
backup=directory/('Caddyfile.'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'.before')
backup.write_bytes(original);backup.chmod(0o600)
staged=directory/'Caddyfile.candidate';staged.write_bytes(candidate);staged.chmod(0o600)
run(['docker','cp',str(staged),container+':/tmp/hcompanion-cd.Caddyfile'])
run(['docker','exec',container,'caddy','validate','--config','/tmp/hcompanion-cd.Caddyfile','--adapter','caddyfile'])
assert config.read_bytes()==original,'Caddy changed during setup'
def write(data):
    with config.open('wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
if candidate!=original:
    write(candidate)
    try:run(['docker','exec',container,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
    except Exception:
        if config.read_bytes()==candidate:
            write(original)
            run(['docker','exec',container,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
        raise
after=run(['docker','ps','--format','{{.ID}} {{.Names}}']).splitlines()
print(json.dumps({'installed':True,'account':user,'caddy_sha256':hashlib.sha256(candidate).hexdigest(),
                  'existing_config_preserved':candidate[:start]==original[:start] and candidate[start+len(candidate_block):]==original[finish:],
                  'container_ids_unchanged':sorted(before)==sorted(after)}))
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ssh-config',type=Path,required=True)
    p.add_argument('--public-key',type=Path,required=True)
    p.add_argument('--expect-caddy-sha',required=True)
    args=p.parse_args()
    key=args.public_key.read_text().strip()
    if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [A-Za-z0-9._-]+)?',key):p.error('Expected an ed25519 public key')
    payload={'public_key':key,'expected_caddy_sha':args.expect_caddy_sha,
             'receiver':base64.b64encode(Path(__file__).with_name('landing_cd.py').read_bytes()).decode()}
    subprocess.run(['ssh','-F',str(args.ssh_config),'-o','BatchMode=yes','-o','ConnectTimeout=8','netcup-holo',
                    'python3 -c '+shlex.quote(REMOTE)],input=json.dumps(payload),text=True,check=True,timeout=120)


if __name__=='__main__':main()
