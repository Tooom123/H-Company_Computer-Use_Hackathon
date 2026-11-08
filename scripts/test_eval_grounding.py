"""Snapshot privacy checks use fake accessibility pages; never inspect a live app."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def evaluation(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("eval_grounding_tested", Path(__file__).with_name("eval_grounding.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.a11y, "page", lambda: pytest.fail("No live accessibility access in tests"))
    return module


@pytest.mark.parametrize("url,expected", [
    ("https://alice:secret@example.test/sessions/123?token=private#credential", "https://example.test/sessions/123"),
    ("http://alice:secret@[::1]:8080/path?secret=yes#private", "http://[::1]:8080/path"),
    ("https://example.test:443/page", "https://example.test:443/page"),
    ("vscode-file://vscode-app/private/local/path", ""),
    ("https://example.test:invalid/path?secret=yes", ""),
])
def test_snapshot_url_omits_credentials_and_nonweb_paths(evaluation, url, expected):
    assert evaluation._snapshot_url(url) == expected


def test_snapshot_has_private_permissions_url_independent_name_and_no_field_values(evaluation, monkeypatch, capsys):
    class Field:
        role, name, frame = "AXTextField", "Search", (1, 2, 3, 4)

        @property
        def value(self):
            pytest.fail("Input values must never be read")

    page = SimpleNamespace(url="https://alice:password@example.test/private-session?token=SECRET#TOKEN",
                           title="Demo page", elements=[Field(), Field()])
    monkeypatch.setattr(evaluation.a11y, "page", lambda: page)
    directory = evaluation.ROOT / "runs" / "snapshots"
    directory.mkdir(parents=True, mode=0o755)
    directory.chmod(0o755)
    path = evaluation.snapshot()
    data = json.loads(path.read_text())
    assert path.stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700
    assert data["url"] == "https://example.test/private-session"
    assert data["elements"] == [{"role": "AXTextField", "name": "Search", "frame": [1, 2, 3, 4]}] * 2
    assert all(secret not in path.name for secret in ("alice", "password", "example", "private-session", "SECRET", "TOKEN"))
    assert "password" not in path.read_text() and "SECRET" not in path.read_text()
    assert "SECRET" not in capsys.readouterr().out
    assert evaluation.load(path)[0].name == "Search"
