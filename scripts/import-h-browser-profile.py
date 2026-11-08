#!/usr/bin/env python3
"""Inspect a reviewed, minimal Linux profile; optionally upload it to H.

This is NOT a sanitizer or an exporter of an everyday browser profile. Build a
dedicated Chromium 150 profile on Linux with --password-store=basic, copy ONLY
H state into a new profile, quit cleanly, minimize and review it before use.
Cookies and fresh Local Storage WAL records are inspected without printing
values. Other stores (including SST, IndexedDB and Session Storage) fail closed.
Passing inspection is not proof that an H login survives the minimization.

Source: https://hub.hcompany.ai/agents-api/browser/profiles
LevelDB: https://github.com/google/leveldb/blob/main/doc/log_format.md
Chromium: components/services/storage/dom_storage/leveldb/local_storage_leveldb.h
"""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import struct
import tempfile
from urllib.parse import urlsplit
import zipfile

NAME = 'h-companion-h-sso'
ORIGIN = 'https://platform.hcompany.ai'
DOMAIN = 'platform.hcompany.ai'
# Exact H authentication domains observed in the dedicated Linux SSO profile.
# A leading cookie domain dot is normalized for inspection only: never rewrite
# the cookie or broaden this to *.hcompany.ai.
COOKIE_DOMAINS = frozenset({'hcompany.ai', 'sso.hcompany.ai', DOMAIN})
LOCAL_STORAGE_DOMAINS = frozenset({'sso.hcompany.ai', DOMAIN})
MAX_BYTES = 64 * 1024 * 1024  # deliberately smaller than H's 1 GB limit
OPTIONS = {'timeout_in_seconds': 30, 'max_retries': 0}


class Refused(Exception):
    """Only fixed, non-sensitive error codes may cross the CLI boundary."""


def private_path(path: Path, *, exists=True) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Refused('symlink_not_allowed')
    if any((p / '.git').exists() for p in path.parents):
        raise Refused('keep_profile_and_journal_outside_git')
    if exists:
        s = path.stat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) not in (0o400, 0o600):
            raise Refused('private_owned_file_mode_0400_or_0600_required')
    return path


def read_private(path: Path) -> bytes:
    path = private_path(path)
    if path.stat().st_size > MAX_BYTES:
        raise Refused('archive_too_large')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, 'rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise Refused('archive_too_large')
        return data
    except BaseException:
        raise


def _crc32c(data: bytes) -> int:
    crc = 0xffffffff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82f63b78 if crc & 1 else 0)
    crc ^= 0xffffffff
    return (((crc >> 15) | (crc << 17)) + 0xa282ead8) & 0xffffffff


def log_records(data: bytes):
    """Read physical records, validating CRC and fragmentation; never salvage."""
    pending = None
    for offset in range(0, len(data), 32768):
        block = data[offset:offset + 32768]
        at = 0
        while at < len(block):
            if len(block) - at < 7:
                if any(block[at:]):
                    raise Refused('invalid_leveldb_trailer')
                break
            checksum, size, kind = struct.unpack_from('<IHB', block, at)
            at += 7
            if kind == size == checksum == 0 and not any(block[at:]):
                break
            chunk = block[at:at + size]
            at += size
            if len(chunk) != size or _crc32c(bytes([kind]) + chunk) != checksum:
                raise Refused('invalid_leveldb_record')
            if kind == 1 and pending is None:
                yield chunk
            elif kind == 2 and pending is None:
                pending = bytearray(chunk)
            elif kind in (3, 4) and pending is not None:
                pending.extend(chunk)
                if kind == 4:
                    yield bytes(pending)
                    pending = None
            else:
                raise Refused('invalid_leveldb_fragment')
    if pending is not None:
        raise Refused('incomplete_leveldb_record')


def _varint(data, at):
    value = 0
    for shift in range(0, 35, 7):
        if at >= len(data):
            break
        b = data[at]
        at += 1
        value |= (b & 127) << shift
        if b < 128:
            return value, at
    raise Refused('invalid_leveldb_varint')


def local_storage_origins(data: bytes) -> Counter:
    result = Counter()
    for record in log_records(data):
        if len(record) < 12:
            raise Refused('invalid_leveldb_batch')
        count = struct.unpack_from('<I', record, 8)[0]
        at = 12
        for _ in range(count):
            if at >= len(record) or record[at] not in (0, 1):
                raise Refused('invalid_leveldb_entry')
            tag = record[at]
            size, at = _varint(record, at + 1)
            key = record[at:at + size]
            at += size
            if len(key) != size:
                raise Refused('invalid_leveldb_key')
            if tag:
                size, at = _varint(record, at)
                at += size  # do not decode or expose values
                if at > len(record):
                    raise Refused('invalid_leveldb_value')
            if key == b'VERSION':
                continue
            if key.startswith(b'_') and b'\0' in key:
                origin = key[1:].split(b'\0', 1)[0]
            elif key.startswith((b'META:', b'METAACCESS:')):
                origin = key.split(b':', 1)[1]
            else:
                raise Refused('unsupported_local_storage_key')
            result[_origin_domain(origin)] += 1
        if at != len(record):
            raise Refused('invalid_leveldb_batch_tail')
    return result


def inspect_manifest(data: bytes):
    """Only fresh LevelDB manifests without tables or compaction keys."""
    count = 0
    for record in log_records(data):
        count += 1
        at = 0
        while at < len(record):
            tag, at = _varint(record, at)
            if tag == 1:  # comparator name, not a user key/value
                size, at = _varint(record, at)
                name = record[at:at + size]
                at += size
                if name != b'leveldb.BytewiseComparator':
                    raise Refused('unsupported_leveldb_comparator')
            elif tag in (2, 3, 4, 9):  # log, next file, sequence, previous log
                _, at = _varint(record, at)
            else:
                raise Refused('nonfresh_leveldb_manifest_not_supported')
    if not count:
        raise Refused('empty_leveldb_manifest')


def _origin_domain(origin):
    try:
        text = origin.decode('ascii') if isinstance(origin, bytes) else origin
        u = urlsplit(text)
        if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password or u.path or u.query or u.fragment or u.port:
            raise ValueError()
        domain = u.hostname
        if not re.fullmatch(r'[a-z0-9.-]{1,253}', domain):
            raise ValueError()
        # A non-HTTPS H origin is not accepted as H authentication state.
        return domain if u.scheme == 'https' else 'http:' + domain
    except (ValueError, UnicodeError):
        raise Refused('unsupported_storage_origin') from None


def cookie_domains(data: bytes) -> Counter:
    with tempfile.TemporaryDirectory(prefix='h-profile-audit-') as tmp:
        path = Path(tmp) / 'Cookies'
        path.write_bytes(data)
        path.chmod(0o600)
        with sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise Refused('invalid_cookie_database')
            if db.execute('PRAGMA freelist_count').fetchone()[0]:
                raise Refused('cookie_database_requires_fresh_rebuild')
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables <= {'cookies', 'meta'} or 'cookies' not in tables:
                raise Refused('unexpected_cookie_tables')
            domains = Counter()
            for host, count in db.execute('SELECT host_key, COUNT(*) FROM cookies GROUP BY host_key'):
                host = host.removeprefix('.')
                if not re.fullmatch(r'[a-z0-9.-]{1,253}', host):
                    raise Refused('invalid_cookie_domain')
                domains[host] += count
            return domains


def inspect_zip_envelope(data: bytes, archive: zipfile.ZipFile):
    """Accept only ordinary, contiguous ZIPs emitted by a seekable ZipFile writer.

    Inspecting member payloads alone misses archive comments, local-only extra
    fields and prefixed/appended bytes. Reject these instead of uploading bytes
    outside the reviewed members. ZIP64 and streaming descriptors are unnecessary
    for this deliberately small archive and are not supported.
    """
    entries = archive.infolist()
    if archive.comment or any(entry.comment for entry in entries):
        raise Refused('zip_comments_not_allowed')
    if len(data) < 22:
        raise Refused('noncanonical_zip_envelope')
    signature, disk, directory_disk, disk_count, count, size, offset, comment_size = struct.unpack_from('<4s4H2IH', data, len(data) - 22)
    if (signature != b'PK\x05\x06' or disk or directory_disk or comment_size
            or disk_count != count or count != len(entries)
            or offset + size != len(data) - 22):
        raise Refused('noncanonical_zip_envelope')
    position = directory_size = 0
    for entry in entries:
        if entry.extra:
            raise Refused('zip_extra_metadata_not_allowed')
        if entry.header_offset != position or position + 30 > offset:
            raise Refused('noncanonical_zip_envelope')
        header = struct.unpack_from('<4s5H3I2H', data, position)
        magic, _, flags, compression, _, _, crc, compressed, expanded, name_size, extra_size = header
        if extra_size:
            raise Refused('zip_extra_metadata_not_allowed')
        if flags & 8:
            raise Refused('zip_streaming_descriptor_not_supported')
        if (magic != b'PK\x03\x04' or flags != entry.flag_bits
                or compression != entry.compress_type or crc != entry.CRC
                or compressed != entry.compress_size or expanded != entry.file_size):
            raise Refused('noncanonical_zip_envelope')
        name = entry.filename.encode('utf-8' if flags & 0x800 else 'cp437')
        if name_size != len(name) or data[position + 30:position + 30 + name_size] != name:
            raise Refused('noncanonical_zip_envelope')
        position += 30 + name_size + compressed
        directory_size += 46 + name_size  # central header, no comments or extras
    if position != offset or directory_size != size:
        raise Refused('noncanonical_zip_envelope')


def inspect_archive(data: bytes) -> dict:
    """Return only counts, domain names, error codes and an archive digest."""
    report = {'profile_name': NAME, 'sha256': hashlib.sha256(data).hexdigest(),
              'required_source_os': 'linux', 'required_browser_version': '150',
              'source_os_verified': False, 'domains': {},
              'cookie_domains': {}, 'local_storage_domains': {},
              'allowed_cookie_domains': sorted(COOKIE_DOMAINS),
              'allowed_local_storage_origins': ['https://' + d for d in sorted(LOCAL_STORAGE_DOMAINS)],
              'issues': [], 'files': 0, 'eligible': False,
              'limitations': ['Fresh H-only reconstruction and manual review are required; this does not prove forensic erasure.',
                              'Authentication compatibility must be tested separately.']}
    domains = Counter()
    cookie_hosts = Counter()
    storage_hosts = Counter()
    allowed_json = {'Local State': {}, 'Default/Preferences': {}}
    cookie_count = 0
    storage_count = 0
    total = 0
    seen = set()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > 1000:
                raise Refused('too_many_archive_entries')
            inspect_zip_envelope(data, archive)
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename or str(path) != info.filename.rstrip('/') or info.filename in seen:
                    raise Refused('unsafe_or_duplicate_archive_path')
                seen.add(info.filename)
                if stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise Refused('archive_special_file_not_allowed')
                if info.flag_bits & 1:
                    raise Refused('encrypted_archive_not_supported')
                if info.is_dir():
                    continue
                report['files'] += 1
                total += info.file_size
                if total > MAX_BYTES or info.file_size > 16 * 1024 * 1024:
                    raise Refused('expanded_archive_too_large')
                payload = archive.read(info)
                name = str(path)
                if name in ('Default/Network/Cookies', 'Default/Cookies'):
                    cookie_count += 1
                    found = cookie_domains(payload)
                    cookie_hosts.update(found)
                    domains.update(found)
                    if set(found) - COOKIE_DOMAINS:
                        report['issues'].append('non_h_authentication_domains_present')
                elif name in allowed_json:
                    # Deliberately empty: real Preferences/Local State may carry
                    # Google account IDs, signin tokens, sync state or extension state.
                    if json.loads(payload) != allowed_json[name]:
                        raise Refused('profile_json_must_be_minimized_to_empty_object')
                elif name == 'Last Version':
                    if payload.strip() != b'150.0.7871.124':
                        raise Refused('chromium_version_mismatch')
                elif re.fullmatch(r'Default/Local Storage/leveldb/[0-9]+\.log', name):
                    found = local_storage_origins(payload)
                    storage_count += sum(found.values())
                    storage_hosts.update(found)
                    domains.update(found)
                    if set(found) - LOCAL_STORAGE_DOMAINS:
                        report['issues'].append('non_h_authentication_domains_present')
                elif name == 'Default/Local Storage/leveldb/LOCK' and payload == b'':
                    pass
                elif name == 'Default/Local Storage/leveldb/CURRENT' and re.fullmatch(rb'MANIFEST-[0-9]+\n', payload):
                    pass
                elif re.fullmatch(r'Default/Local Storage/leveldb/MANIFEST-[0-9]+', name):
                    # These LevelDB structural records contain version metadata,
                    # not user data. Verify framing; no generic byte/string scan.
                    inspect_manifest(payload)
                else:
                    report['issues'].append('unsupported_profile_file_or_storage')
            if cookie_count > 1:
                report['issues'].append('multiple_cookie_databases')
            if cookie_count == 0 and storage_count == 0:
                report['issues'].append('no_inspectable_authentication_store')
    except Refused as exc:
        report['issues'].append(str(exc))
    except (zipfile.BadZipFile, RuntimeError, ValueError, sqlite3.Error, KeyError, UnicodeError):
        report['issues'].append('invalid_or_unsupported_archive')
    report['domains'] = dict(sorted(domains.items()))
    report['cookie_domains'] = dict(sorted(cookie_hosts.items()))
    report['local_storage_domains'] = dict(sorted(storage_hosts.items()))
    if not (set(cookie_hosts) & COOKIE_DOMAINS or set(storage_hosts) & LOCAL_STORAGE_DOMAINS):
        report['issues'].append('h_authentication_state_missing')
    report['issues'] = sorted(set(report['issues']))
    report['eligible'] = not report['issues']
    return report


def _write_journal(path, state):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def upload_archive(data, report, journal, client, *, reviewed_sha256, post=None):
    """No retries after uncertain writes; a completed journal is idempotent."""
    if not report['eligible'] or reviewed_sha256 != report['sha256'] or hashlib.sha256(data).hexdigest() != report['sha256']:
        raise Refused('eligible_reviewed_archive_hash_required')
    journal = private_path(journal, exists=journal.exists())
    if not journal.parent.is_dir() or stat.S_IMODE(journal.parent.stat().st_mode) & 0o077:
        raise Refused('private_journal_directory_required')
    lock = journal.with_suffix('.lock')
    if lock.exists():
        private_path(lock)
    with os.fdopen(os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if journal.exists():
            state = json.loads(read_private(journal))
            if state.get('archive_sha256') != report['sha256']:
                raise Refused('journal_belongs_to_another_archive')
            if state.get('state') == 'complete':
                return state
            raise Refused('previous_upload_requires_manual_reconciliation_no_retry')
        state = {'profile_name': NAME, 'archive_sha256': report['sha256'], 'state': 'initiate_pending'}
        _write_journal(journal, state)
        try:
            upload = client.browser_profiles.initiate_browser_profile_upload(request_options=OPTIONS)
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', upload.profile_id):
                raise Refused('invalid_profile_id')
            state.update(profile_id=upload.profile_id, state='upload_pending')
            _write_journal(journal, state)
            url = urlsplit(upload.upload_url)
            # The trusted H API supplies the presigned storage destination. Never
            # reuse H Authorization headers and never follow storage redirects.
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.port not in (None, 443):
                raise Refused('invalid_presigned_upload_url')
            if post is None:
                import requests
                post = requests.post
            response = post(upload.upload_url, data=upload.upload_fields,
                            files={'file': (NAME + '.zip', io.BytesIO(data), 'application/zip')},
                            timeout=(15, 120), allow_redirects=False)
            if not 200 <= response.status_code < 300:
                raise Refused('storage_upload_failed')
            state['state'] = 'complete_pending'
            _write_journal(journal, state)
            profile = client.browser_profiles.complete_browser_profile_upload(
                profile_id=upload.profile_id, name=NAME, browser_name='chromium', browser_version='150',
                request_options=OPTIONS)
            if profile.id != upload.profile_id:
                raise Refused('completed_profile_id_mismatch')
            state['state'] = 'complete'
            _write_journal(journal, state)
            return state
        except BaseException:
            # Keep the last pending state. Never log HTTP errors, signed fields,
            # response bodies, cookies or authentication values.
            raise Refused('upload_unconfirmed_inspect_private_journal_do_not_retry') from None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True, help='Private h-companion-h-sso.zip outside Git')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--reviewed-sha256', help='Digest of the freshly reconstructed archive after manual review')
    p.add_argument('--journal', type=Path)
    args = p.parse_args(argv)
    try:
        if args.archive.name != NAME + '.zip':
            raise Refused('dedicated_profile_archive_name_required')
        data = read_private(args.archive)
        report = inspect_archive(data)
        if not args.apply:
            print(json.dumps(report, indent=2))
            return 0 if report['eligible'] else 2
        if not args.journal or not args.reviewed_sha256:
            raise Refused('apply_requires_private_journal_and_reviewed_sha256')
        key = os.environ.get('HAI_API_KEY')
        if not key:
            raise Refused('HAI_API_KEY_required')
        from hai_agents import Client
        client = Client(api_key=key, base_url='https://agp.eu.hcompany.ai')
        result = upload_archive(data, report, args.journal, client, reviewed_sha256=args.reviewed_sha256)
        print(json.dumps(result))
        return 0
    except Refused as exc:
        print(json.dumps({'error': str(exc)}))
        return 2
    except Exception:
        print(json.dumps({'error': 'local_inspection_failed_no_secret_details_printed'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
