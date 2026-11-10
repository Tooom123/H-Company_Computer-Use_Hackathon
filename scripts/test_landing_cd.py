import base64
from html.parser import HTMLParser
import importlib.util
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pytest

spec = importlib.util.spec_from_file_location('landing_cd', Path(__file__).with_name('landing_cd.py'))
cd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cd)


@pytest.fixture
def release(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    for name in cd.ASSETS:
        (source / name).write_text('public-' + name)
    root = tmp_path / 'public'
    (root / 'releases' / ('a' * 64)).mkdir(parents=True)
    (root / 'current').symlink_to('releases/' + 'a' * 64)
    return cd.package(source, 'b' * 40), root, source


def test_release_switch_is_atomic_and_preserves_previous_release(release):
    payload, root, _ = release
    result = cd.receive(payload, root)
    assert result['previous_release'] == 'releases/' + 'a' * 64
    assert (root / 'releases' / ('a' * 64)).is_dir()
    assert set(p.name for p in (root / 'current').iterdir()) == set(cd.ASSETS)
    assert cd.receive(payload, root)['release_sha256'] == payload['digest']  # repeatable


@pytest.mark.parametrize('change', ['extra', 'traversal', 'digest', 'oversize', 'version', 'revision'])
def test_bad_payload_cannot_change_current_release(release, change):
    payload, root, _ = release
    if change == 'extra': payload['files']['.env'] = 'c2VjcmV0'
    if change == 'traversal': payload['files']['../index.html'] = payload['files'].pop('index.html')
    if change == 'digest': payload['digest'] = 'c' * 64
    if change == 'oversize': payload['files']['main.js'] = base64.b64encode(b'x' * (cd.MAX_ASSET + 1)).decode()
    if change == 'version': payload['version'] = True
    if change == 'revision': payload['revision'] = 'main; bad'
    with pytest.raises(ValueError): cd.receive(payload, root)
    assert (root / 'current').readlink() == Path('releases/' + 'a' * 64)


def test_linked_release_or_asset_is_rejected(release):
    payload, root, source = release
    (root / 'releases' / payload['digest']).symlink_to(source)
    with pytest.raises(ValueError): cd.receive(payload, root)
    assert (root / 'current').readlink() == Path('releases/' + 'a' * 64)


def test_package_never_includes_other_repository_files(release):
    _, _, source = release
    (source / '.env').write_text('private')
    assert set(cd.package(source, 'b' * 40)['files']) == set(cd.ASSETS)
    (source / 'main.js').unlink()
    (source / 'main.js').symlink_to(source / '.env')
    with pytest.raises(ValueError): cd.package(source, 'b' * 40)


def test_package_includes_same_origin_html_assets():
    class AssetParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if attrs.get('src'):
                self.urls.append(attrs['src'])
            resource_links = {'stylesheet', 'icon', 'preload', 'modulepreload', 'manifest'}
            if tag == 'link' and resource_links.intersection(attrs.get('rel', '').split()) and attrs.get('href'):
                self.urls.append(attrs['href'])

    source = Path(__file__).resolve().parents[1] / 'landing'
    payload = cd.package(source, 'b' * 40)
    parser = AssetParser()
    parser.feed((source / 'index.html').read_text())
    origin = 'https://hcompanion.help/'
    dependencies = {
        url.path.removeprefix('/')
        for asset in parser.urls
        if (url := urlsplit(urljoin(origin, asset))).netloc == urlsplit(origin).netloc
    }
    assert dependencies, 'The HTML dependency check must discover local assets'
    assert not (missing := dependencies - payload['files'].keys()), f'Unpublished HTML assets: {sorted(missing)}'
