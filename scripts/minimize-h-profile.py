#!/usr/bin/env python3
"""Build a fresh COOKIE-ONLY H profile from a closed, dedicated Linux profile.

Never reads credentials from a personal browser, decodes cookie values, copies
SQLite pages, uploads anything, or claims that authentication still works.
All local/session storage, IndexedDB, browser history, preferences and account
metadata are intentionally omitted. Reopen a separate clone to verify login.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys

COOKIE_DOMAINS = frozenset({'hcompany.ai', 'sso.hcompany.ai', 'platform.hcompany.ai'})
VERSION = b'150.0.7871.124'
MAX_COOKIE_BYTES = 32 * 1024 * 1024


class Refused(Exception):
    """Fixed safe error codes only; never include source values or paths."""


def checked_path(path: Path) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Refused('symlink_not_allowed')
    if any((p / '.git').exists() for p in (path, *path.parents)):
        raise Refused('profile_must_be_outside_git')
    return path


def read_file(path: Path, maximum: int) -> bytes:
    checked_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise Refused('invalid_source_file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise Refused('source_file_too_large')
    return value


def write_file(path: Path, payload: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(payload)


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def rebuild_cookies(source: Path, destination: Path) -> dict:
    """Copy selected rows into new pages, preserving original column values."""
    checked_path(source)
    info = source.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_COOKIE_BYTES:
        raise Refused('invalid_cookie_database_file')
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = source.with_name(source.name + suffix)
        if sidecar.is_symlink():
            raise Refused('cookie_database_sidecar_present_close_browser_first')
        if sidecar.exists():
            sidecar_info = sidecar.stat()
            # SQLite may leave a zero-byte rollback journal after a clean close.
            # It has no pending pages. WAL/SHM and nonempty journals remain
            # ambiguous; never reopen the source read-write to repair them.
            if suffix == '-journal' and stat.S_ISREG(sidecar_info.st_mode) and sidecar_info.st_size == 0:
                continue
            raise Refused('cookie_database_sidecar_present_close_browser_first')
    before = (info.st_ino, info.st_size, info.st_mtime_ns)
    with sqlite3.connect(source.as_uri() + '?mode=ro&immutable=1', uri=True) as original:
        original.execute('PRAGMA query_only=ON')
        original.execute('PRAGMA trusted_schema=OFF')
        if original.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise Refused('invalid_cookie_database')
        objects = original.execute("SELECT type,name,tbl_name,sql FROM sqlite_master").fetchall()
        tables = {name for kind, name, _, _ in objects if kind == 'table'}
        if tables != {'cookies', 'meta'}:
            raise Refused('unexpected_cookie_tables')
        if any(kind not in ('table', 'index') or table not in tables
               for kind, _, table, _ in objects):
            raise Refused('unexpected_cookie_schema_objects')
        columns = {table: [r[1] for r in original.execute('PRAGMA table_info(' + quoted(table) + ')')]
                   for table in tables}
        if 'host_key' not in columns['cookies'] or columns['meta'] != ['key', 'value']:
            raise Refused('unsupported_cookie_schema')
        # Chromium meta holds integer schema versions, not site/session state.
        metadata = original.execute('SELECT key,value FROM meta').fetchall()
        if any(key not in ('version', 'last_compatible_version', 'mmap_status')
               or not re.fullmatch(r'-?[0-9]{1,10}', str(value)) for key, value in metadata):
            raise Refused('unsupported_cookie_metadata')
        allowed_hosts = sorted(COOKIE_DOMAINS | {'.' + host for host in COOKIE_DOMAINS})
        select_columns = ','.join(quoted(c) for c in columns['cookies'])
        total = original.execute('SELECT COUNT(*) FROM cookies').fetchone()[0]
        rows = original.execute('SELECT ' + select_columns + ' FROM cookies WHERE host_key IN ('
                                + ','.join('?' for _ in allowed_hosts) + ')', allowed_hosts).fetchall()
        if not rows:
            raise Refused('no_h_cookies_found')
        host_position = columns['cookies'].index('host_key')
        domains = Counter(row[host_position].removeprefix('.') for row in rows)
        write_file(destination, b'')
        with sqlite3.connect(destination) as fresh:
            fresh.execute('PRAGMA journal_mode=DELETE')
            fresh.execute('PRAGMA trusted_schema=OFF')
            for kind, _, _, sql in objects:
                if kind == 'table':
                    if not sql or not re.match(r'^CREATE\s+TABLE\s', sql, re.I):
                        raise Refused('unsupported_cookie_schema')
                    fresh.execute(sql)
            fresh.executemany('INSERT INTO meta (key,value) VALUES (?,?)', metadata)
            fresh.executemany('INSERT INTO cookies (' + select_columns + ') VALUES ('
                              + ','.join('?' for _ in columns['cookies']) + ')', rows)
            for kind, _, _, sql in objects:
                if kind == 'index' and sql is not None:
                    if not re.match(r'^CREATE\s+(?:UNIQUE\s+)?INDEX\s', sql, re.I):
                        raise Refused('unsupported_cookie_index')
                    fresh.execute(sql)
            # These are header metadata, not old database pages.
            for pragma in ('user_version', 'application_id'):
                fresh.execute('PRAGMA ' + pragma + '=' + str(original.execute('PRAGMA ' + pragma).fetchone()[0]))
            fresh.commit()
            if fresh.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise Refused('rebuilt_database_invalid')
            if fresh.execute('PRAGMA freelist_count').fetchone()[0] != 0:
                raise Refused('rebuilt_database_has_free_pages')
    after = source.stat()
    if before != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise Refused('source_changed_during_rebuild')
    return {'source_cookie_count': total, 'retained_cookie_count': len(rows),
            'omitted_cookie_count': total - len(rows), 'cookie_domains': dict(sorted(domains.items()))}


def minimize(source: Path, output: Path, *, source_closed: bool = False) -> dict:
    if not source_closed:
        raise Refused('explicit_closed_dedicated_profile_confirmation_required')
    source, output = checked_path(source), checked_path(output)
    if not source.is_dir() or not output.parent.is_dir():
        raise Refused('source_and_output_parent_must_exist')
    if output.exists() or output.is_symlink():
        raise Refused('output_already_exists')
    if source == output or source in output.parents or output in source.parents:
        raise Refused('source_and_output_must_be_separate')
    # A remaining singleton is ambiguous; never delete it or guess its owner.
    if any((source / name).exists() or (source / name).is_symlink()
           for name in ('SingletonLock', 'SingletonSocket', 'SingletonCookie')):
        raise Refused('browser_singleton_present_close_browser_first')
    if read_file(source / 'Last Version', 64).strip() != VERSION:
        raise Refused('chromium_version_mismatch')
    candidates = [source / 'Default' / 'Network' / 'Cookies', source / 'Default' / 'Cookies']
    for path in candidates:
        checked_path(path)
    present = [path for path in candidates if path.exists()]
    if len(present) != 1:
        raise Refused('exactly_one_cookie_database_required')
    os.mkdir(output, 0o700)
    try:
        os.mkdir(output / 'Default', 0o700)
        relative = present[0].relative_to(source)
        if relative.parts[-2] == 'Network':
            os.mkdir(output / 'Default' / 'Network', 0o700)
        report = rebuild_cookies(present[0], output / relative)
        write_file(output / 'Local State', b'{}')
        write_file(output / 'Default' / 'Preferences', b'{}')
        write_file(output / 'Last Version', VERSION)
        report.update(mode='cookie_only_fresh_rebuild', source_modified=False,
                      local_storage_included=False, indexeddb_included=False,
                      authentication_verified=False, compatible_with_h_verified=False,
                      allowed_cookie_domains=sorted(COOKIE_DOMAINS))
        return report
    except BaseException:
        # The path was newly created by this call. Never delete a pre-existing
        # output or any file from the source profile.
        shutil.rmtree(output)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source-closed', action='store_true',
                        help='Confirm this is a dedicated Linux profile and Chromium has exited.')
    args = parser.parse_args(argv)
    try:
        report = minimize(args.source, args.output, source_closed=args.source_closed)
    except Refused as exc:
        print(json.dumps({'state': 'refused', 'reason': str(exc)}))
        return 2
    except Exception:
        # SQLite and filesystem errors can include paths, SQL or stored values.
        print(json.dumps({'state': 'refused', 'reason': 'rebuild_failed_no_details_logged'}))
        return 2
    print(json.dumps({'state': 'complete', **report}, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
