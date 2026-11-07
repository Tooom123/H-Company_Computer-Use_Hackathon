import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import struct
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location('h_profile_import', Path(__file__).with_name('import-h-browser-profile.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def varint(n):
    out = bytearray()
    while n >= 128:
        out.append((n & 127) | 128)
        n >>= 7
    return bytes(out + bytes([n]))


def physical(payload, kind=1):
    return struct.pack('<IHB', m._crc32c(bytes([kind]) + payload), len(payload), kind) + payload


def wal(*keys):
    entries = b''
    for key in keys:
        entries += b'\1' + varint(len(key)) + key + b'\6' + b'SECRET'
    return physical(struct.pack('<QI', 0, len(keys)) + entries)


def archive(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        for name, value in files.items():
            z.writestr(name, value)
    return data.getvalue()


def clean_files():
    prefix = 'Default/Local Storage/leveldb/'
    comparator = b'leveldb.BytewiseComparator'
    return {'Local State': b'{}', 'Default/Preferences': b'{}', 'Last Version': b'150.0.7871.124',
            prefix + '000003.log': wal(b'_https://platform.hcompany.ai\0\1token'),
            prefix + 'CURRENT': b'MANIFEST-000001\n', prefix + 'LOCK': b'',
            prefix + 'MANIFEST-000001': physical(b'\1' + varint(len(comparator)) + comparator)}


@pytest.fixture
def clean():
    data = archive(clean_files())
    report = m.inspect_archive(data)
    assert report['eligible'], report
    return data, report


def test_only_h_origin_and_no_values_in_report(clean):
    _, report = clean
    assert report['domains'] == {m.DOMAIN: 1}
    assert report['required_source_os'] == 'linux'
    assert report['source_os_verified'] is False
    assert 'SECRET' not in json.dumps(report)


@pytest.mark.parametrize('domain', ['accounts.google.com', 'mail.google.com', 'hcompany.ai', 'auth.hcompany.ai'])
def test_other_origin_blocks(domain):
    files = {'Default/Local Storage/leveldb/000003.log': wal(('_https://' + domain + '\0token').encode())}
    report = m.inspect_archive(archive(files))
    assert not report['eligible']
    assert 'non_h_authentication_domains_present' in report['issues']
    assert domain in report['domains']


def test_deleted_google_record_still_blocks():
    key = b'_https://accounts.google.com\0token'
    batch = struct.pack('<QI', 0, 1) + b'\0' + varint(len(key)) + key
    report = m.inspect_archive(archive({'Default/Local Storage/leveldb/000003.log': physical(batch)}))
    assert 'non_h_authentication_domains_present' in report['issues']


@pytest.mark.parametrize('path', ['Default/IndexedDB/google.leveldb/000001.ldb', 'Default/Session Storage/000001.log',
    'Default/Login Data', 'Default/History', 'Default/Cache/cache', 'Default/Local Storage/leveldb/000007.ldb',
    'Default/Network/Cookies-wal', 'Profile 2/Preferences'])
def test_unknown_storage_blocks(clean, path):
    files = clean_files()
    files[path] = b'SECRET'
    report = m.inspect_archive(archive(files))
    assert not report['eligible']
    assert report['issues'] == ['unsupported_profile_file_or_storage']


@pytest.mark.parametrize('path', ['../Cookies', '/Default/Cookies', 'Default\\Cookies'])
def test_zip_paths_rejected(path):
    assert 'unsafe_or_duplicate_archive_path' in m.inspect_archive(archive({path: b''}))['issues']


@pytest.mark.parametrize('location', ['archive_comment', 'entry_comment', 'entry_extra', 'prefix', 'suffix'])
def test_zip_envelope_cannot_carry_uninspected_data(location):
    marker = b'SYNTHETIC_METADATA_NOT_AUTH_STATE'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        for name, value in clean_files().items():
            entry = zipfile.ZipInfo(name)
            if location == 'entry_comment':
                entry.comment = marker
            if location == 'entry_extra':
                entry.extra = struct.pack('<HH', 0xcafe, len(marker)) + marker
            z.writestr(entry, value)
        if location == 'archive_comment':
            z.comment = marker
    data = stream.getvalue()
    if location == 'prefix':
        data = marker + data
    elif location == 'suffix':
        data += marker
    report = m.inspect_archive(data)
    assert not report['eligible']
    expected = ('zip_comments_not_allowed' if 'comment' in location else
                'zip_extra_metadata_not_allowed' if location == 'entry_extra' else 'noncanonical_zip_envelope')
    assert expected in report['issues']
    assert marker.decode() not in json.dumps(report)


def test_local_only_extra_metadata_is_refused():
    name = 'Default/Local Storage/leveldb/000003.log'
    payload = wal(b'_https://platform.hcompany.ai\0token')
    data = bytearray(archive({name: payload}))
    extra = struct.pack('<HH', 0xcafe, 6) + b'HIDDEN'
    insertion = 30 + len(name.encode())
    struct.pack_into('<H', data, 28, len(extra))
    data[insertion:insertion] = extra
    directory_offset = struct.unpack_from('<I', data, len(data) - 6)[0]
    struct.pack_into('<I', data, len(data) - 6, directory_offset + len(extra))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.infolist()[0].extra == b''  # central metadata alone would miss it
        assert z.read(name) == payload
    assert 'zip_extra_metadata_not_allowed' in m.inspect_archive(bytes(data))['issues']


@pytest.mark.parametrize('compression', [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_standard_seekable_zip_builder_remains_compatible(compression):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=compression) as z:
        z.writestr('Default/', b'')
        for name, value in clean_files().items():
            z.writestr(name, value)
    report = m.inspect_archive(stream.getvalue())
    assert report['eligible'], report['issues']


def test_crc_corruption_and_partial_records():
    data = bytearray(wal(b'_https://platform.hcompany.ai\0token'))
    data[-1] ^= 1
    with pytest.raises(m.Refused, match='invalid_leveldb_record'):
        m.local_storage_origins(bytes(data))
    with pytest.raises(m.Refused, match='incomplete_leveldb_record'):
        list(m.log_records(physical(b'part', kind=2)))


def test_fragmented_record():
    payload = struct.pack('<QI', 0, 1) + b'\1\7VERSION\1' + b'1'
    first = physical(payload[:8], 2)
    # Fill first block with zeros to model an end-of-block first fragment.
    data = first + bytes(32768 - len(first)) + physical(payload[8:], 4)
    assert m.local_storage_origins(data) == {}


def test_manifest_user_data_or_sst_rejected():
    with pytest.raises(m.Refused, match='nonfresh_leveldb_manifest'):
        m.inspect_manifest(physical(b'\7\1'))


def test_nonempty_preferences_not_uploaded():
    report = m.inspect_archive(archive({'Default/Preferences': b'{"account_info":[{"token":"SECRET"}]}'}))
    assert 'profile_json_must_be_minimized_to_empty_object' in report['issues']
    assert 'SECRET' not in json.dumps(report)


def test_cookie_domains_only(tmp_path):
    path = tmp_path / 'cookies'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE cookies(host_key TEXT, value TEXT)')
        db.executemany('INSERT INTO cookies VALUES (?,?)', [(m.DOMAIN, 'SECRET'), ('.google.com', 'GOOGLESECRET')])
    report = m.inspect_archive(archive({'Default/Network/Cookies': path.read_bytes()}))
    assert report['domains'] == {'google.com': 1, m.DOMAIN: 1}
    assert not report['eligible']
    assert 'SECRET' not in json.dumps(report)


def test_exact_h_sso_cookie_domains_accepted_without_rewrite(tmp_path):
    path = tmp_path / 'cookies'
    original_hosts = ['.hcompany.ai', '.sso.hcompany.ai', 'sso.hcompany.ai', 'platform.hcompany.ai']
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE cookies(host_key TEXT, value TEXT)')
        db.executemany('INSERT INTO cookies VALUES (?,?)', [(host, 'SECRET') for host in original_hosts])
    before = path.read_bytes()
    report = m.inspect_archive(archive({'Default/Network/Cookies': before}))
    assert report['eligible'], report
    assert report['cookie_domains'] == {'hcompany.ai': 1, 'sso.hcompany.ai': 2, 'platform.hcompany.ai': 1}
    assert report['local_storage_domains'] == {}
    assert path.read_bytes() == before
    assert report['source_os_verified'] is False
    assert 'SECRET' not in json.dumps(report)


@pytest.mark.parametrize('host', ['.google.com', '.accounts.google.com', '.youtube.com', 'other.hcompany.ai',
                                  'nested.sso.hcompany.ai', 'hcompany.ai.attacker.test', '..hcompany.ai'])
def test_cookie_allowlist_is_exact(tmp_path, host):
    path = tmp_path / 'cookies'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE cookies(host_key TEXT, value TEXT)')
        db.execute('INSERT INTO cookies VALUES (?,?)', (host, 'SECRET'))
    report = m.inspect_archive(archive({'Default/Network/Cookies': path.read_bytes()}))
    assert not report['eligible']
    assert 'non_h_authentication_domains_present' in report['issues']


@pytest.mark.parametrize('origin,allowed', [
    ('https://platform.hcompany.ai', True), ('https://sso.hcompany.ai', True),
    ('https://hcompany.ai', False), ('http://sso.hcompany.ai', False),
    ('https://nested.sso.hcompany.ai', False), ('https://accounts.google.com', False),
])
def test_local_storage_scope_remains_https_exact(origin, allowed):
    data = wal(('_' + origin + '\0token').encode())
    report = m.inspect_archive(archive({'Default/Local Storage/leveldb/000003.log': data}))
    assert report['eligible'] is allowed
    assert report['cookie_domains'] == {}
    assert 'SECRET' not in json.dumps(report)


def test_private_file_and_git_refusals(tmp_path):
    private = tmp_path / 'h-companion-h-sso.zip'
    private.write_bytes(b'x')
    private.chmod(0o644)
    with pytest.raises(m.Refused, match='mode'):
        m.read_private(private)
    private.chmod(0o600)
    link = tmp_path / 'linked'
    link.symlink_to(private)
    with pytest.raises(m.Refused, match='symlink'):
        m.read_private(link)
    (tmp_path / '.git').mkdir()
    with pytest.raises(m.Refused, match='outside_git'):
        m.read_private(private)


def client():
    fake = Mock()
    fake.browser_profiles.initiate_browser_profile_upload.return_value = SimpleNamespace(
        profile_id='profile-123', upload_url='https://bucket.s3.amazonaws.com/',
        upload_fields={'policy': 'SIGNATURE_SECRET'}, upload_expires_in=3600)
    fake.browser_profiles.complete_browser_profile_upload.return_value = SimpleNamespace(id='profile-123')
    return fake


def test_upload_contract_and_idempotent_journal(clean, tmp_path):
    tmp_path.chmod(0o700)
    data, report = clean
    api, post = client(), Mock(return_value=SimpleNamespace(status_code=204))
    journal = tmp_path / 'upload.json'
    out = m.upload_archive(data, report, journal, api, reviewed_sha256=report['sha256'], post=post)
    assert out['state'] == 'complete'
    assert m.upload_archive(data, report, journal, api, reviewed_sha256=report['sha256'], post=post) == out
    assert api.browser_profiles.initiate_browser_profile_upload.call_count == 1
    args = post.call_args.kwargs
    assert args['allow_redirects'] is False and 'headers' not in args
    assert args['data'] == {'policy': 'SIGNATURE_SECRET'}
    assert args['files']['file'][2] == 'application/zip'
    assert 'SECRET' not in journal.read_text()
    assert 'upload_url' not in journal.read_text()
    assert api.browser_profiles.complete_browser_profile_upload.call_args.kwargs['browser_version'] == '150'


def test_uncertain_create_never_retried(clean, tmp_path):
    tmp_path.chmod(0o700)
    data, report = clean
    api = client()
    api.browser_profiles.initiate_browser_profile_upload.side_effect = RuntimeError('TOKEN_SECRET')
    journal = tmp_path / 'upload.json'
    for _ in range(2):
        with pytest.raises(m.Refused) as error:
            m.upload_archive(data, report, journal, api, reviewed_sha256=report['sha256'])
        assert 'SECRET' not in str(error.value)
    assert api.browser_profiles.initiate_browser_profile_upload.call_count == 1
    assert json.loads(journal.read_text())['state'] == 'initiate_pending'


def test_unreviewed_digest_has_no_side_effect(clean, tmp_path):
    data, report = clean
    api = client()
    with pytest.raises(m.Refused, match='eligible_reviewed_archive'):
        m.upload_archive(data, report, tmp_path / 'journal', api, reviewed_sha256='wrong')
    api.browser_profiles.initiate_browser_profile_upload.assert_not_called()


def test_redirect_not_followed_or_completed(clean, tmp_path):
    tmp_path.chmod(0o700)
    data, report = clean
    api = client()
    with pytest.raises(m.Refused):
        m.upload_archive(data, report, tmp_path / 'upload.json', api, reviewed_sha256=report['sha256'],
                         post=Mock(return_value=SimpleNamespace(status_code=302)))
    api.browser_profiles.complete_browser_profile_upload.assert_not_called()


def test_cli_dry_run_does_not_require_api_key(clean, tmp_path, capsys, monkeypatch):
    data, report = clean
    monkeypatch.delenv('HAI_API_KEY', raising=False)
    path = tmp_path / (m.NAME + '.zip')
    path.write_bytes(data)
    path.chmod(0o600)
    assert m.main(['--archive', str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['sha256'] == report['sha256']
    assert 'SECRET' not in json.dumps(result)
