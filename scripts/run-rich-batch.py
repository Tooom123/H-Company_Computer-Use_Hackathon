#!/usr/bin/env python3
"""Run an explicitly approved read-only rich campaign on one worker, sequentially.

No human feedback is generated. Reviewers attach separate agent-review.json files.
Desktop workers require the demo in front; isolated browser workers do not use the Mac desktop.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

TERMINAL = {'resolved', 'escalated', 'stopped', 'failed', 'preflight_failed'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-root', type=Path, required=True)
    parser.add_argument('--campaign', required=True)
    parser.add_argument('--scenarios', nargs='+', required=True)
    parser.add_argument('--approve-read-only', action='store_true')
    parser.add_argument('--state-check-command', type=Path, required=True,
                        help='Private JSON array of argv for the existing read-only status command')
    args = parser.parse_args()
    if not args.approve_read_only or any(s not in {f'R{i:02d}' for i in range(1, 11)} for s in args.scenarios):
        parser.error('Explicit read-only approval and R01–R10 cases are required.')
    if not args.campaign.replace('-', '').replace('_', '').isalnum():
        parser.error('Invalid campaign identifier.')
    os.umask(0o077)
    root = args.private_root.expanduser().resolve()
    if any((p / '.git').exists() for p in (root, *root.parents)):
        parser.error('Private output must stay outside Git.')
    token = (root / 'pilot-token').read_text().strip()
    runtime = json.loads((root / 'runtime.json').read_text())
    port = runtime.get('port', 8767)
    if type(port) is not int or not 1024 <= port <= 65535:
        parser.error('Invalid private worker port.')
    output = root / 'campaigns' / args.campaign
    output.mkdir(parents=True, exist_ok=False)
    status_command = json.loads(args.state_check_command.read_text())
    if not isinstance(status_command, list) or not all(isinstance(v, str) for v in status_command):
        parser.error('State check must be a JSON argv list.')

    def api(method, path, data=None):
        req = urllib.request.Request(f'http://127.0.0.1:{port}' + path, method=method,
                                     data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.load(response)

    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    def baseline(label):
        result = subprocess.run(status_command, capture_output=True, text=True, timeout=45, check=True)
        value = json.loads(result.stdout)
        rich = value['odoo']['rich']
        save(label + '-state.json', value)
        if (value['odoo']['database'] != 'holo_hackathon_rich' or
                rich['snapshot'] != rich['expected_snapshot'] or rich['counts'] != rich['expected_counts']):
            raise RuntimeError('Demo identity or baseline changed; batch stopped for review.')
        # This fingerprint covers only the fields in rich_snapshot.py, not every ORM field.

    info = api('GET', '/pilot/status')
    if info['busy'] or info.get('simulated') or info.get('environment', {}).get('id') != 'odoo-rich-v2.1':
        raise RuntimeError('Expected an idle real pilot on rich v2.1.')
    cards = {c['id']: c for c in api('GET', '/pilot/scenarios')}
    if any(s not in cards or cards[s]['requires_reference'] or cards[s].get('depends_on') for s in args.scenarios):
        raise RuntimeError('Batch requires independent rich read-only scenarios.')
    save('campaign.json', {'created_at': datetime.now(timezone.utc).isoformat(), 'scenarios': args.scenarios,
                          'runtime': info, 'approval_source': 'user_requested_read_only_batch',
                          'human_feedback': None, 'ready_for_sft': False})
    rows, active = [], None
    try:
        baseline('before')
        for scenario in args.scenarios:
            if (output / 'STOP').exists():
                break
            made = api('POST', '/pilot/episodes', {'scenario_id': scenario, 'goal': cards[scenario]['prompt']})
            active = made['session_id']
            row = {'scenario': scenario, 'session_id': active, 'state': made['state'],
                   'export_status': 'pending', 'agent_review': 'pending', 'human_feedback': None}
            rows.append(row)
            save('results.json', rows)
            deadline = time.monotonic() + 35
            while made['state'] not in {'awaiting_approval', *TERMINAL}:
                if time.monotonic() > deadline:
                    raise RuntimeError('Plan preparation exceeded time limit.')
                time.sleep(1)
                made = api('GET', '/pilot/episodes/' + active)
            if made['state'] == 'awaiting_approval':
                api('POST', f'/interventions/{active}/approve', {
                    'approved': True,
                    'scope_note': 'Utilisateur : série séquentielle R01–R10 en lecture seule sur Odoo enrichi. '
                                  'Évaluation IA séparée du futur retour humain. Aucun envoi externe, mutation métier ou identifiant.'})
            print(json.dumps({'scenario': scenario, 'session_id': active, 'event': 'started'}), flush=True)
            deadline, last, heartbeat = time.monotonic() + 560, None, 0
            while True:
                snap = api('GET', '/pilot/episodes/' + active)
                if snap['state'] != last or time.monotonic() - heartbeat > 30:
                    row.update(state=snap['state'], export_status=snap.get('pilot', {}).get('export_status', 'pending'))
                    save('results.json', rows)
                    print(json.dumps({'scenario': scenario, 'state': snap['state'], 'steps': len(snap.get('steps', []))}), flush=True)
                    last, heartbeat = snap['state'], time.monotonic()
                if snap['state'] in TERMINAL and (snap.get('report_ready') or snap['state'] == 'preflight_failed'):
                    break
                if time.monotonic() > deadline or (output / 'STOP').exists():
                    raise RuntimeError('Stop requested or episode time limit exceeded.')
                time.sleep(2)
            # Archive normally finishes quickly; retain an explicit state if it does not.
            until = time.monotonic() + 90
            while snap['pilot']['export_status'] in {'pending', 'exporting'} and time.monotonic() < until:
                time.sleep(2)
                snap = api('GET', '/pilot/episodes/' + active)
            row.update(state=snap['state'], export_status=snap['pilot']['export_status'])
            save('results.json', rows)
            print(json.dumps({**row, 'event': 'finished'}), flush=True)
            active = None
            baseline(scenario + '-after')
    except BaseException as error:
        if active:
            row['interruption'] = type(error).__name__
            try:
                api('POST', f'/interventions/{active}/stop', {'reason': 'Batch interrompu ; conserver la trace.'})
                until = time.monotonic() + 45
                while time.monotonic() < until:
                    stopped = api('GET', '/pilot/episodes/' + active)
                    row.update(state=stopped['state'], export_status=stopped.get('pilot', {}).get('export_status', 'unknown'))
                    if stopped['state'] in TERMINAL:
                        print(json.dumps({'event': 'stop_confirmed', 'session_id': active, 'state': stopped['state']}), flush=True)
                        break
                    time.sleep(1)
                else:
                    print('Stop remains pending; inspect the pilot before resuming.', flush=True)
            except Exception:
                row['stop_confirmation'] = 'unknown'
                print('Stop request could not be confirmed; inspect the pilot before resuming.', flush=True)
        raise
    finally:
        save('results.json', rows)
    print(json.dumps({'event': 'batch_finished', 'episodes': len(rows), 'output': str(output)}), flush=True)


if __name__ == '__main__':
    main()
