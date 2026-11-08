"""A Finder launch must not silently reuse a developer's restricted rehearsal."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def launcher(monkeypatch):
    spec = importlib.util.spec_from_file_location('v2_launcher_profile',
                                                Path(__file__).with_name('run-h-platform-coach-v2.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv('HCS_V2_REHEARSAL', raising=False)
    monkeypatch.delenv('HCS_V2_READONLY_REHEARSAL', raising=False)
    return module


@pytest.mark.parametrize('active', [None, {},
    {'read_only_rehearsal': True, 'text_rehearsal': True},
    {'read_only_rehearsal': False, 'text_rehearsal': True},
])
def test_normal_launch_refuses_unknown_or_test_runtime_without_stopping_it(launcher, monkeypatch, tmp_path, active):
    monkeypatch.setattr(launcher, 'control_status', lambda _: {'runtime_profile': active})
    monkeypatch.setattr(launcher, 'owns_runtime', lambda *args: True)
    spawn, kill = Mock(), Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    monkeypatch.setattr(launcher.os, 'kill', kill)
    with pytest.raises(RuntimeError, match='different or unknown test mode'):
        launcher.start_runtime('/unused/python', tmp_path, 8792, 'alt_r')
    spawn.assert_not_called()
    kill.assert_not_called()


def test_matching_normal_runtime_is_reused(launcher, monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, 'control_status', lambda _: {'runtime_profile': launcher.runtime_profile()})
    monkeypatch.setattr(launcher, 'owns_runtime', lambda *args: True)
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    assert launcher.start_runtime('/unused/python', tmp_path, 8792, 'alt_r') is False
    spawn.assert_not_called()


def test_restricted_launch_cannot_reuse_normal_runtime(launcher, monkeypatch):
    monkeypatch.setenv('HCS_V2_READONLY_REHEARSAL', '1')
    monkeypatch.setenv('HCS_V2_REHEARSAL', '1')
    with pytest.raises(RuntimeError, match='different or unknown test mode'):
        launcher.check_runtime_profile({'runtime_profile': {'read_only_rehearsal': False, 'text_rehearsal': False}})


@pytest.mark.parametrize('flags,expected', [([], (False, False)),
    (['--rehearsal'], (False, True)), (['--read-only-rehearsal'], (True, True))])
def test_cli_flags_determine_mode_not_parent_environment(launcher, monkeypatch, tmp_path, flags, expected):
    monkeypatch.setenv('HCS_V2_READONLY_REHEARSAL', '1')
    monkeypatch.setenv('HCS_V2_REHEARSAL', '1')
    monkeypatch.setattr(launcher.sys, 'platform', 'darwin')
    monkeypatch.setattr(launcher.sys, 'argv', ['launcher', '--backend-only', '--private-root', str(tmp_path), *flags])
    monkeypatch.setattr(launcher, 'python_executable', lambda: '/unused/python')
    captured = []
    monkeypatch.setattr(launcher, 'start_runtime', lambda *args: captured.append(launcher.runtime_profile()))
    assert launcher.main() == 0
    assert captured == [{'read_only_rehearsal': expected[0], 'text_rehearsal': expected[1]}]
