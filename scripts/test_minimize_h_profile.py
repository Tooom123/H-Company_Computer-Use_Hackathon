import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import stat
import zipfile

import pytest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load('minimize_h', 'minimize-h-profile.py')
audit = load('audit_h', 'import-h-browser-profile.py')


@pytest.fixture
def profile(tmp_path):
    root = tmp_path / 'dedicated'
    network = root / 'Default' / 'Network'
    network.mkdir(parents=True)
    (root / 'Last Version').write_bytes(m.VERSION)
    (root / 'Local State').write_text('{"account_info":"GOOGLEPROFILESECRET"}')
    (root / 'Default' / 'Preferences').write_text('{"account":"GOOGLEPREFSECRET"}')
    (root / 'Default' / 'History').write_text('GOOGLEHISTORYSECRET')
    with sqlite3.connect(network / 'Cookies') as db:
        db.execute('CREATE TABLE meta(key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR)')
        db.executemany('INSERT INTO meta VALUES (?,?)', [('version', '24'), ('last_compatible_version', '24')])
        db.execute('CREATE TABLE cookies(host_key TEXT NOT NULL, name TEXT NOT NULL, encrypted_value BLOB NOT NULL, value TEXT, expires_utc INTEGER)')
        db.execute('CREATE UNIQUE INDEX cookies_unique ON cookies(host_key,name)')
        db.executemany('INSERT INTO cookies VALUES (?,?,?,?,?)', [
            ('.hcompany.ai', 'access_token', b'v10\x00HOPAQUE', '', 123),
            ('.hcompany.ai', 'refresh_token', b'v10\x00HREFRESH', '', 456),
            ('.hcompany.ai', 'session_id', b'v10\x00HSESSION', '', 789),
            ('sso.hcompany.ai', 'XSRF', b'v10\x00HXSRF', '', 987),
            ('.sso.hcompany.ai', 'cognito', b'v10\x00HCOGNITO', '', 654),
            ('accounts.google.com', 'SID', b'GOOGLECOOKIESECRET', '', 321),
            ('other.hcompany.ai', 'not_h_auth', b'OTHERSECRET', '', 100),
            ('..hcompany.ai', 'invalid_domain', b'BADSECRET', '', 100),
        ])
        # Old deleted bytes/free pages must never survive a page-level copy.
        db.execute('INSERT INTO cookies VALUES (?,?,?,?,?)', ('google.com', 'deleted', b'DELETEDSECRET' * 2000, '', 1))
        db.commit()
        db.execute('DELETE FROM cookies WHERE name="deleted"')
    return root


def zip_profile(root):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as z:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(root).as_posix())
    return payload.getvalue()


def test_fresh_h_only_values_exact_source_unchanged(profile, tmp_path):
    before = {p.relative_to(profile): p.read_bytes() for p in profile.rglob('*') if p.is_file()}
    output = tmp_path / 'minimal'
    report = m.minimize(profile, output, source_closed=True)
    assert report['retained_cookie_count'] == 5
    assert report['omitted_cookie_count'] == 3
    assert report['cookie_domains'] == {'hcompany.ai': 3, 'sso.hcompany.ai': 2}
    assert report['authentication_verified'] is False
    assert report['local_storage_included'] is False
    assert 'SECRET' not in json.dumps(report)
    assert before == {p.relative_to(profile): p.read_bytes() for p in profile.rglob('*') if p.is_file()}
    with sqlite3.connect(profile / 'Default/Network/Cookies') as source, sqlite3.connect(output / 'Default/Network/Cookies') as dest:
        expected = [row for row in source.execute('SELECT * FROM cookies') if row[0] in {'.hcompany.ai', 'sso.hcompany.ai', '.sso.hcompany.ai'}]
        assert sorted(dest.execute('SELECT * FROM cookies')) == sorted(expected)
        assert dest.execute('PRAGMA freelist_count').fetchone()[0] == 0
        assert dest.execute('SELECT sql FROM sqlite_master WHERE name="cookies_unique"').fetchone() == source.execute('SELECT sql FROM sqlite_master WHERE name="cookies_unique"').fetchone()
    payload = zip_profile(output)
    assert all(marker not in payload for marker in (b'GOOGLE', b'DELETEDSECRET', b'OTHERSECRET', b'BADSECRET'))
    assert audit.inspect_archive(payload)['eligible'] is True
    assert (output / 'Local State').read_bytes() == b'{}'
    assert (output / 'Default/Preferences').read_bytes() == b'{}'
    for path in output.rglob('*'):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)


def test_other_storage_never_copied(profile, tmp_path):
    storage = profile / 'Default/Local Storage/leveldb'
    storage.mkdir(parents=True)
    (storage / '000001.ldb').write_bytes(b'GOOGLESECRET')
    indexed = profile / 'Default/IndexedDB'
    indexed.mkdir()
    (indexed / 'google.ldb').write_bytes(b'GOOGLESECRET')
    output = tmp_path / 'minimal'
    report = m.minimize(profile, output, source_closed=True)
    assert not (output / 'Default/Local Storage').exists()
    assert not (output / 'Default/IndexedDB').exists()
    assert not report['indexeddb_included']


@pytest.mark.parametrize('sidecar', ['-wal', '-shm'])
def test_source_sidecars_fail_closed(profile, tmp_path, sidecar):
    (profile / ('Default/Network/Cookies' + sidecar)).write_bytes(b'')
    output = tmp_path / 'minimal'
    with pytest.raises(m.Refused, match='sidecar_present'):
        m.minimize(profile, output, source_closed=True)
    assert not output.exists()


def test_empty_regular_rollback_journal_accepted_and_not_copied(profile, tmp_path):
    journal = profile / 'Default/Network/Cookies-journal'
    journal.write_bytes(b'')
    output = tmp_path / 'minimal'
    report = m.minimize(profile, output, source_closed=True)
    assert report['retained_cookie_count'] == 5
    assert journal.read_bytes() == b''
    assert not (output / 'Default/Network/Cookies-journal').exists()
    assert audit.inspect_archive(zip_profile(output))['eligible']


@pytest.mark.parametrize('kind', ['nonempty', 'symlink_empty', 'symlink_missing', 'directory'])
def test_other_rollback_journals_refused(profile, tmp_path, kind):
    journal = profile / 'Default/Network/Cookies-journal'
    if kind == 'nonempty':
        journal.write_bytes(b'\x00')
    elif kind == 'directory':
        journal.mkdir()
    else:
        target = tmp_path / 'journal-target'
        if kind == 'symlink_empty':
            target.write_bytes(b'')
        journal.symlink_to(target)
    output = tmp_path / 'minimal'
    with pytest.raises(m.Refused, match='sidecar_present'):
        m.minimize(profile, output, source_closed=True)
    assert not output.exists()


def test_output_not_overwritten(profile, tmp_path):
    output = tmp_path / 'minimal'
    output.mkdir()
    (output / 'keep').write_text('KEEP')
    with pytest.raises(m.Refused, match='already_exists'):
        m.minimize(profile, output, source_closed=True)
    assert (output / 'keep').read_text() == 'KEEP'


@pytest.mark.parametrize('name', ['SingletonLock', 'SingletonSocket', 'SingletonCookie'])
def test_open_browser_refused(profile, tmp_path, name):
    (profile / name).symlink_to(tmp_path / 'absent')
    with pytest.raises(m.Refused, match='singleton_present'):
        m.minimize(profile, tmp_path / 'minimal', source_closed=True)


def test_explicit_confirmation_required(profile, tmp_path):
    with pytest.raises(m.Refused, match='confirmation_required'):
        m.minimize(profile, tmp_path / 'minimal')


def test_wrong_version(profile, tmp_path):
    (profile / 'Last Version').write_bytes(b'151.0.0')
    with pytest.raises(m.Refused, match='version_mismatch'):
        m.minimize(profile, tmp_path / 'minimal', source_closed=True)


def test_symlink_cookie_refused(profile, tmp_path):
    original = profile / 'Default/Network/Cookies'
    external = tmp_path / 'external'
    original.rename(external)
    original.symlink_to(external)
    with pytest.raises(m.Refused, match='symlink'):
        m.minimize(profile, tmp_path / 'minimal', source_closed=True)


@pytest.mark.parametrize('schema', ['CREATE TABLE surprise(secret TEXT)', 'CREATE VIEW exposed AS SELECT * FROM cookies',
                                  'CREATE TRIGGER secret AFTER INSERT ON cookies BEGIN SELECT 1; END'])
def test_extra_schema_refused(profile, tmp_path, schema):
    with sqlite3.connect(profile / 'Default/Network/Cookies') as db:
        db.execute(schema)
    output = tmp_path / 'minimal'
    with pytest.raises(m.Refused):
        m.minimize(profile, output, source_closed=True)
    assert not output.exists()


def test_meta_secret_refused(profile, tmp_path):
    with sqlite3.connect(profile / 'Default/Network/Cookies') as db:
        db.execute('INSERT INTO meta VALUES (?,?)', ('google', 'GOOGLESECRET'))
    output = tmp_path / 'minimal'
    assert m.main(['--source', str(profile), '--output', str(output), '--source-closed']) == 2
    assert not output.exists()


def test_no_cookie_match_refused(profile, tmp_path):
    with sqlite3.connect(profile / 'Default/Network/Cookies') as db:
        db.execute("DELETE FROM cookies WHERE host_key LIKE '%hcompany.ai'")
    with pytest.raises(m.Refused, match='no_h_cookies'):
        m.minimize(profile, tmp_path / 'minimal', source_closed=True)


def test_legacy_cookie_path(profile, tmp_path):
    (profile / 'Default/Network/Cookies').rename(profile / 'Default/Cookies')
    output = tmp_path / 'minimal'
    m.minimize(profile, output, source_closed=True)
    assert audit.inspect_archive(zip_profile(output))['eligible']


def test_safe_error_output(profile, tmp_path, capsys):
    (profile / 'Default/Network/Cookies').write_bytes(b'GOOGLESECRET')
    assert m.main(['--source', str(profile), '--output', str(tmp_path / 'minimal'), '--source-closed']) == 2
    logged = capsys.readouterr().out
    assert 'GOOGLESECRET' not in logged and str(profile) not in logged


def test_source_output_must_not_nest(profile):
    with pytest.raises(m.Refused, match='must_be_separate'):
        m.minimize(profile, profile / 'minimal', source_closed=True)
