#!/usr/bin/env python3
"""Provision an explicitly human-operated H SSO session, separate from benchmarks.

Never reads personal Chrome cookies or asks for a Google password. Requires an
empty H profile inventory so it cannot overwrite an existing default. Login
screens are not downloaded by this helper or exposed in the company console.
"""
import argparse
import json
import os
from pathlib import Path
import uuid

from dotenv import dotenv_values
from hai_agents import Client

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'status', 'finish'])
    p.add_argument('--private-root', type=Path, required=True)
    p.add_argument('--browser-profile-id', help='Explicit existing dedicated profile to refresh; never select a profile implicitly.')
    p.add_argument('--retry-rejected-create', action='store_true', help='Only after a confirmed 4xx rejection; preserves the idempotency key.')
    args = p.parse_args()
    os.umask(0o077)
    root = args.private_root.expanduser().resolve()
    if any((x / '.git').exists() for x in (root, *root.parents)):
        raise SystemExit('Keep authentication state outside Git.')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / 'manual-login.json'
    key = dotenv_values(ROOT / 'app/.env').get('HAI_API_KEY')
    if not key:
        raise SystemExit('Missing HAI_API_KEY.')
    c = Client(api_key=key)
    options = {'timeout_in_seconds': 20, 'max_retries': 0}
    if args.action == 'prepare':
        if path.exists() and not args.retry_rejected_create:
            raise SystemExit('A login preparation already exists; inspect it before creating another.')
        profiles = c.browser_profiles.list_browser_profiles(request_options=options)
        if profiles.total and not args.browser_profile_id:
            raise SystemExit('Existing H profiles found; explicitly select one instead of changing a default.')
        if args.browser_profile_id and args.browser_profile_id not in {x.id for x in profiles.profiles}:
            raise SystemExit('The explicitly selected profile is not present in this account.')
        profile_config = ({'browser_profile_id': args.browser_profile_id, 'use_default_browser_profile': False,
                           'persist_browser_profile': True} if args.browser_profile_id
                          else {'use_default_browser_profile': True})
        state = json.loads(path.read_text()) if path.exists() else {'idempotency_key': 'companion-login-' + uuid.uuid4().hex, 'state': 'creating'}
        if state.get('session_id'):
            raise SystemExit('This preparation already owns a session; do not create another.')
        path.write_text(json.dumps(state))
        session = c.sessions.create_session(
            agent={'name': 'companion-human-login', 'description': 'Dedicated browser for manual Google SSO sign-in.', 'model': 'holo4-35b-a3b',
                   'instructions': 'This browser is for a human to sign in. Use go_to once to open https://platform.hcompany.ai/auth/login so the login screen is visible in Agent View. Do not click sign-in buttons, type, inspect secrets, access other sites or log in. Once the login page is visible answer only: Ready for manual sign-in.',
                   'environments': [{'id': 'login-browser', 'kind': 'web', 'host': 'cloud',
                                     'headless': False, 'lazy': False, 'start_url': 'https://platform.hcompany.ai/auth/login',
                                     'mode': {'type': 'visual', 'width': 1280, 'height': 832},
                                     **profile_config}]},
            messages='Open the H login page once with go_to so the human can see it in Agent View. Then leave the browser untouched and answer that manual sign-in is ready.',
            idle_timeout_s=900, max_steps=3, max_time_s=60, queue=False,
            idempotency_key=state['idempotency_key'], request_options=options)
        state.update(session_id=session.id, agent_view_url=session.agent_view_url,
                     state=session.status.status, purpose='manual_authentication_not_benchmark')
        path.write_text(json.dumps(state, indent=2))
        print(json.dumps(state, ensure_ascii=False))
        return
    state = json.loads(path.read_text())
    sid = state.get('session_id')
    if not sid:
        raise SystemExit('Creation is unconfirmed; inspect the saved idempotency key before retrying.')
    if args.action == 'finish':
        # v2 cancellation stops this owned login session and saves its profile;
        # it does not use the legacy trajectory deletion endpoint.
        c.sessions.cancel_session(sid, request_options=options)
    session = c.sessions.get_session(sid, request_options=options)
    profiles = c.browser_profiles.list_browser_profiles(request_options=options)
    state.update(state=session.status.status, agent_view_url=session.agent_view_url,
                 profiles=[{'id': x.id, 'name': x.name, 'is_default': x.is_default}
                           for x in profiles.profiles])
    path.write_text(json.dumps(state, indent=2))
    print(json.dumps(state, ensure_ascii=False))


if __name__ == '__main__':
    main()
