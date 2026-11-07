#!/usr/bin/env python3
"""Archive completed H cloud sessions locally; never run or modify an agent.

Stdlib only. API key is read from HAI_API_KEY, never passed on the command line.
Cloud export preserves what H returns, not a guarantee of the original model input.
Local/Spark sessions require a separate recorder and cannot use this cloud exporter.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_ORIGIN = 'https://agp.eu.hcompany.ai'
API_BASE = API_ORIGIN + '/api/v2'
TERMINAL = {'completed', 'failed', 'timed_out', 'interrupted'}
MAX_BYTES = 64 * 1024 * 1024
SESSION_ID = re.compile(r'^[A-Za-z0-9_-]{1,160}$')


class ExportError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def checked_url(url: str, session_id: str, *, api: bool = False) -> tuple[str, bool]:
    """Only documented H resources or S3; never send H credentials to storage."""
    url = urljoin(API_ORIGIN, url)
    p = urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ExportError('Resource must use HTTPS without credentials or a custom port')
    if any(part in ('.', '..') for part in unquote(unquote(p.path)).split('/')):
        raise ExportError('Resource path traversal is not allowed')
    if p.hostname == 'agp.eu.hcompany.ai':
        prefix = '/api/v2/sessions/' + quote(session_id, safe='')
        allowed = p.path.startswith(prefix + '/resources/')
        if api:
            allowed = p.path in {prefix, prefix + '/status', prefix + '/events'}
        if not allowed:
            raise ExportError('Resource is not owned by this H session')
        return url, True
    if not api and p.hostname and p.hostname.endswith('.amazonaws.com'):
        return url, False
    raise ExportError('Unsupported resource host; archive manually without forwarding H credentials')


class CloudClient:
    def __init__(self, api_key: str):
        self.key = api_key
        self.opener = build_opener(NoRedirect())

    def read(self, url: str, session_id: str, *, api: bool = False) -> bytes:
        for _ in range(6):
            url, auth = checked_url(url, session_id, api=api)
            request = Request(url, headers={'Authorization': f'Bearer {self.key}'} if auth else {})
            try:
                with self.opener.open(request, timeout=60) as response:
                    raw = response.read(MAX_BYTES + 1)
            except HTTPError as error:
                if not api and error.code in (301, 302, 303, 307, 308) and error.headers.get('Location'):
                    url = urljoin(url, error.headers['Location'])
                    error.close()
                    continue
                # Do not print an error body, a signed URL, or headers.
                error.close()
                raise ExportError(f'HTTP {error.code} while archiving a session resource') from None
            if len(raw) > MAX_BYTES:
                raise ExportError('Response exceeds the 64 MiB per-resource limit')
            return raw
        raise ExportError('Too many resource redirects')

    def get_json(self, session_id: str, suffix: str = '') -> tuple[dict, bytes]:
        raw = self.read(f'{API_BASE}/sessions/{quote(session_id, safe="")}{suffix}', session_id, api=True)
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ExportError('Unexpected JSON response shape')
        return value, raw

    def image(self, session_id: str, image: dict) -> bytes:
        source = image['source']
        if image['type'] == 'url':
            return self.read(source, session_id)
        if image['type'] == 'base64':
            if source.startswith('data:'):
                source = source.split(',', 1)[1]
            raw = base64.b64decode(source, validate=True)
            if len(raw) > MAX_BYTES:
                raise ExportError('Inline image exceeds the 64 MiB limit')
            return raw
        raise ExportError('Unsupported image type')


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def walk(value, pointer=''):
    yield pointer or '/', value
    if isinstance(value, dict):
        for key, item in value.items():
            key = str(key).replace('~', '~0').replace('/', '~1')
            yield from walk(item, pointer + '/' + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, pointer + '/' + str(index))


def image_extension(raw: bytes) -> str:
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if raw.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
        return 'webp'
    if raw.startswith((b'GIF87a', b'GIF89a')):
        return 'gif'
    raise ExportError('Downloaded resource is not a recognized raster image')


def archive_session(client, session_id: str, root: Path, *, size=200) -> dict:
    if not SESSION_ID.fullmatch(session_id) or session_id.startswith('sim_'):
        raise ExportError('Expected a real H cloud session ID, not a simulated ID')
    dest = root / session_id
    dest.mkdir(mode=0o700)
    (dest / 'images').mkdir(mode=0o700)
    (dest / 'pages').mkdir(mode=0o700)
    manifest = {'session_id': session_id, 'archive_complete': False, 'ready_for_sft': False,
                'issues': [], 'images': [], 'event_count': 0}
    try:
        session, raw = client.get_json(session_id)
        (dest / 'session.json').write_bytes(raw)
        status, raw = client.get_json(session_id, '/status')
        (dest / 'status-before.json').write_bytes(raw)
        manifest['status'] = status.get('status')
        manifest['subagent_session_ids'] = status.get('subagent_session_ids') or []
        if status.get('status') not in TERMINAL:
            manifest['issues'].append({'kind': 'session_not_terminal'})
        events = []
        total = None
        for page_number in range(1, 10001):
            suffix = '/events?' + urlencode({'page': page_number, 'size': size, 'sort': 'timestamp'})
            page, raw = client.get_json(session_id, suffix)
            (dest / 'pages' / f'{page_number:05}.json').write_bytes(raw)
            if not isinstance(page.get('items'), list) or type(page.get('total')) is not int or page.get('page') != page_number:
                raise ExportError('Unexpected event pagination schema')
            if total is None:
                total = page['total']
            if page['total'] != total:
                raise ExportError('Event count changed during export; retry after the session ends')
            events.extend(page['items'])
            if len(events) >= total:
                if len(events) != total:
                    raise ExportError('Event pagination returned too many events')
                break
            if not page['items']:
                raise ExportError('Empty event page before the announced total')
        else:
            raise ExportError('Pagination safety limit reached')
        (dest / 'events.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8')
        manifest['event_count'] = len(events)
        for index, event in enumerate(events):
            for pointer, value in walk(event):
                if not isinstance(value, dict):
                    continue
                if value.get('truncated') is True:
                    manifest['issues'].append({'kind': 'upstream_truncation', 'event': index, 'pointer': pointer})
                if value.get('output_artifact_path'):
                    manifest['issues'].append({'kind': 'tool_artifact_needs_local_copy', 'event': index, 'pointer': pointer})
                if value.get('type') in ('url', 'base64') and isinstance(value.get('source'), str):
                    entry = {'event': index, 'pointer': pointer, 'source_type': value['type']}
                    try:
                        raw = client.image(session_id, value)
                        digest = hashlib.sha256(raw).hexdigest()
                        relative = f'images/{digest}.{image_extension(raw)}'
                        (dest / relative).write_bytes(raw)
                        entry.update({'path': relative, 'sha256': digest, 'bytes': len(raw)})
                    except Exception as error:
                        # Exception strings may contain signed URLs or transport credentials.
                        entry['error'] = type(error).__name__
                        manifest['issues'].append({'kind': 'image_not_archived', 'event': index, 'pointer': pointer})
                    manifest['images'].append(entry)
        after, raw = client.get_json(session_id, '/status')
        (dest / 'status-after.json').write_bytes(raw)
        if after != status:
            manifest['issues'].append({'kind': 'session_status_changed_during_export'})
        if not manifest['images']:
            manifest['issues'].append({'kind': 'no_images_found_verify_expected_observations'})
        # Raw content may already omit prompts or compacted history. Never certify SFT readiness here.
        manifest['archive_complete'] = not manifest['issues']
    except Exception as error:
        manifest['issues'].append({'kind': 'export_failed', 'error_type': type(error).__name__,
            **({'message': str(error)} if isinstance(error, ExportError) else {})})
    finally:
        manifest['files'] = {str(p.relative_to(dest)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                             for p in sorted(dest.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
        write_json(dest / 'manifest.json', manifest)
    return manifest


def private_destination(path: Path) -> Path:
    path = path.expanduser().resolve()
    if any((parent / '.git').exists() for parent in [path, *path.parents]):
        raise ExportError('Trace output must be outside any Git worktree')
    if path.exists():
        raise ExportError('Output directory already exists; choose a fresh archive path')
    path.mkdir(parents=True, mode=0o700)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-id', action='append', default=[])
    parser.add_argument('--report', type=Path, help='Matteo report.json; exports every h_session_id, including verification')
    parser.add_argument('--output', required=True, type=Path, help='New PRIVATE directory outside Git')
    args = parser.parse_args(argv)
    ids = list(args.session_id)
    report = None
    if args.report:
        report = json.loads(args.report.read_text(encoding='utf-8'))
        if report.get('simulated') is not False:
            raise ExportError('Cloud export requires a report explicitly marked simulated=false')
        ids.extend(report.get('h_session_ids') or [])
    if not ids or not all(isinstance(sid, str) and SESSION_ID.fullmatch(sid) and not sid.startswith('sim_') for sid in ids):
        raise ExportError('Supply real H cloud session IDs or a real report containing them')
    key = os.environ.get('HAI_API_KEY', '').strip()
    if not key:
        raise ExportError('HAI_API_KEY is required in the environment')
    os.umask(0o077)
    root = private_destination(args.output)
    if report is not None:
        write_json(root / 'report.json', report)
    client = CloudClient(key)
    queue = list(dict.fromkeys(ids))
    completed = {}
    while queue:
        sid = queue.pop(0)
        if sid in completed:
            continue
        result = archive_session(client, sid, root)
        completed[sid] = result
        for child in result.get('subagent_session_ids', []):
            if not isinstance(child, str) or not SESSION_ID.fullmatch(child) or child.startswith('sim_'):
                result['issues'].append({'kind': 'invalid_subagent_id'})
                result['archive_complete'] = False
                write_json(root / sid / 'manifest.json', result)
            elif child not in completed and child not in queue:
                queue.append(child)
        if len(completed) + len(queue) > 100:
            raise ExportError('More than 100 linked sessions; inspect the archive before continuing')
    write_json(root / 'labels.json', {'simulated': False, 'task_success_user': None, 'useful': None,
        'objective_success': None, 'objective_evidence': [], 'human_corrections': [],
        'comment': '', 'reviewed': False, 'allow_training': False, 'include_for_training': False})
    summary = {'exported_at': datetime.now(timezone.utc).isoformat(), 'source': 'h-cloud',
        'sessions': {sid: {'archive_complete': value['archive_complete'], 'event_count': value['event_count'],
                           'issues': len(value['issues'])} for sid, value in completed.items()},
        'ready_for_sft': False}
    write_json(root / 'export.json', summary)
    print(json.dumps({'output': str(root), 'sessions': len(completed),
                      'complete': all(item['archive_complete'] for item in completed.values()), 'ready_for_sft': False}))
    return 0 if all(item['archive_complete'] for item in completed.values()) else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except ExportError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
    except Exception as error:
        print(f'Export stopped ({type(error).__name__}); inspect the private partial archive.', file=sys.stderr)
        raise SystemExit(2)
