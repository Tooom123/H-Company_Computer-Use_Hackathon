"""Detached launcher ownership checks; all subprocesses, sockets and HTTP are simulated."""

import importlib.util
import json
from pathlib import Path
import subprocess
import socket
from types import SimpleNamespace

import pytest


def test_port_probe_refuses_live_listener_but_allows_tcp_time_wait():
    spec = importlib.util.spec_from_file_location("launcher_port_probe", Path(__file__).with_name("start-devin-companion.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 0))
        port = server.getsockname()[1]
        server.listen(1)
        assert module.port_busy(port) is True
        with socket.create_connection(('127.0.0.1', port), timeout=1) as client:
            peer, _ = server.accept()
            peer.close()  # Server initiates close; its connection can remain in TIME_WAIT.
            assert client.recv(1) == b''
    assert module.port_busy(port) is False


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("start_devin_companion_tested", Path(__file__).with_name("start-devin-companion.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path / "checkout")
    monkeypatch.setattr(module, "PRIVATE", tmp_path)
    monkeypatch.setattr(module, "control_status", lambda: pytest.fail("Test must explicitly model HTTP state"))
    monkeypatch.setattr(module, "port_busy", lambda port: pytest.fail("Unexpected real socket probe"))
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: pytest.fail("Unexpected process launch"))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("Unexpected process launch"))
    module.test_private = tmp_path
    return module


def metadata(launcher, **updates):
    value = {"pid": 1234, "software": "cognition", "surface": "devin-desktop",
             "native_bundle_id": launcher.BUNDLE, **updates}
    (launcher.test_private / "runtime.json").write_text(json.dumps(value))
    return value


def status(**updates):
    return {"agent": {"pid": 1234, "observe_only": True, **updates}, "voice": {"ptt_key": "ctrl+shift+h"}}


@pytest.mark.parametrize("contents", ["null", "[]", '"text"', "42", "{broken json"])
def test_malformed_or_nonobject_metadata_is_an_empty_mapping(launcher, contents):
    target = launcher.test_private / "runtime.json"
    target.write_text(contents)
    assert launcher.read_json(target) == {}
    assert launcher.read_json(launcher.test_private / "missing.json") == {}


@pytest.mark.parametrize("value", [[], ["unexpected"], "unexpected", 7, None])
def test_malformed_status_sections_are_not_ready_or_owned(launcher, value):
    assert launcher.owns_runtime({"agent": value}, metadata(launcher)) is False
    assert launcher.ready({"voice": value}) is False


@pytest.mark.parametrize("updates", [
    {"pid": 9999}, {"software": "hcompany"}, {"surface": "browser"},
    {"native_bundle_id": "com.google.Chrome"}, {"native_bundle_id": None},
])
def test_mismatched_runtime_is_rejected_without_spawn(launcher, monkeypatch, updates):
    metadata(launcher, **updates)
    monkeypatch.setattr(launcher, "control_status", status)
    with pytest.raises(RuntimeError, match="different coach"):
        launcher.start_runtime("/unused/python", launcher.test_private)


def test_takeover_enabled_runtime_is_not_reused(launcher, monkeypatch):
    metadata(launcher)
    monkeypatch.setattr(launcher, "control_status", lambda: status(observe_only=False))
    with pytest.raises(RuntimeError, match="different coach"):
        launcher.start_runtime("/unused/python", launcher.test_private)


def test_matching_ready_runtime_reused_without_spawn_or_socket_probe(launcher, monkeypatch):
    metadata(launcher)
    monkeypatch.setattr(launcher, "control_status", status)
    assert launcher.start_runtime("/unused/python", launcher.test_private) is False


@pytest.mark.parametrize("busy_port", [8780, 8781])
def test_occupied_port_does_not_spawn_or_stop_any_process(launcher, monkeypatch, busy_port):
    monkeypatch.setattr(launcher, "control_status", lambda: None)
    checked = []
    monkeypatch.setattr(launcher, "port_busy", lambda port: checked.append(port) or port == busy_port)
    with pytest.raises(RuntimeError, match="occupied"):
        launcher.start_runtime("/unused/python", launcher.test_private)
    assert busy_port in checked


def test_runtime_spawn_is_detached_and_uses_argument_list_with_private_log(launcher, monkeypatch):
    metadata(launcher)
    replies = iter([None, status()])
    monkeypatch.setattr(launcher, "control_status", lambda: next(replies))
    monkeypatch.setattr(launcher, "port_busy", lambda _: False)
    calls = []
    process = SimpleNamespace(pid=1234, poll=lambda: None)

    def popen(command, **kwargs):
        assert isinstance(command, list)
        assert kwargs.get("shell", False) is False
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.STDOUT
        assert kwargs["start_new_session"] is True and kwargs["close_fds"] is True
        assert Path(kwargs["stdout"].name).parent == launcher.test_private
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    assert launcher.start_runtime("/test/python with spaces", launcher.test_private) is True
    assert len(calls) == 1
    command = calls[0][0]
    assert command[0] == "/test/python with spaces"
    assert command[-1] == str(launcher.test_private)
    assert "--native-devin" in command and command[command.index("--software") + 1] == "cognition"
    assert command[command.index("--input-language") + 1] == "fr-en"


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_failed_or_slow_new_process_is_not_killed(launcher, monkeypatch, failure):
    monkeypatch.setattr(launcher, "control_status", lambda: None)
    monkeypatch.setattr(launcher, "port_busy", lambda _: False)
    calls = []
    process = SimpleNamespace(pid=1234, poll=lambda: 1 if failure == "exit" else None,
                              kill=lambda: pytest.fail("Never kill after a launch/readiness failure"),
                              terminate=lambda: pytest.fail("Never terminate after a launch/readiness failure"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw)) or process)
    times = iter([0, 0, 50])
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="could not start|still starting"):
        launcher.start_runtime("/test/python", launcher.test_private)
    assert len(calls) == 1


def test_new_launch_requires_its_own_pid_even_when_metadata_matches_another_coach(launcher, monkeypatch):
    metadata(launcher, pid=7777)
    replies = iter([None, status(pid=7777)])
    monkeypatch.setattr(launcher, "control_status", lambda: next(replies))
    monkeypatch.setattr(launcher, "port_busy", lambda _: False)
    process = SimpleNamespace(pid=1234, poll=lambda: None,
                              kill=lambda: pytest.fail("No process may be killed"),
                              terminate=lambda: pytest.fail("No process may be killed"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: process)
    times = iter([0, 0, 50])
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="still starting"):
        launcher.start_runtime("/test/python", launcher.test_private)


def test_existing_not_ready_runtime_waits_without_duplicate_listener(launcher, monkeypatch):
    metadata(launcher)
    waiting = status()
    waiting["voice"] = {"ptt_key": None}
    replies = iter([waiting, status()])
    monkeypatch.setattr(launcher, "control_status", lambda: next(replies))
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    assert launcher.start_runtime("/unused/python", launcher.test_private) is False


def test_desktop_cleans_node_mode_and_passes_matching_loopback_environment(launcher, monkeypatch):
    binary = launcher.ROOT / "desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setenv("ELECTRON_RUN_AS_NODE", "1")
    monkeypatch.setenv("HCS_CONTROL_URL", "http://127.0.0.1:8768")
    calls = []

    def popen(command, **kwargs):
        env = kwargs["env"]
        assert "ELECTRON_RUN_AS_NODE" not in env
        assert env["HCS_CONTROL_URL"] == "http://127.0.0.1:8780"
        assert env["HCS_BACKEND_URL"] == "http://127.0.0.1:8781"
        assert env["HCS_PILOT_KIND"] == "devin-native"
        assert env["HCS_PILOT_PYTHON"] == "/test/python"
        assert isinstance(command, list) and kwargs.get("shell", False) is False
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["start_new_session"] is True
        calls.append((command, kwargs))
        return SimpleNamespace(wait=lambda timeout: 0)

    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    launcher.start_desktop("/test/python", launcher.test_private)
    assert len(calls) == 1
    assert calls[0][0] == [str(binary), str(launcher.ROOT / "desktop")]


def test_python_probe_keeps_virtualenv_symlink_and_does_not_run_shell(launcher, monkeypatch):
    binary = launcher.test_private / "venv/bin/python"
    binary.parent.mkdir(parents=True)
    executable = launcher.test_private / "python-base"
    executable.touch(mode=0o700)
    binary.symlink_to(executable)
    (launcher.test_private / "launcher.json").write_text(json.dumps({"python": str(binary)}))
    monkeypatch.delenv("HCS_PILOT_PYTHON", raising=False)
    calls = []

    def run(command, **kwargs):
        assert command[0] == str(binary)
        assert kwargs.get("shell", False) is False
        assert all(kwargs[key] == subprocess.DEVNULL for key in ("stdin", "stdout", "stderr"))
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.python_executable(launcher.test_private) == str(binary)
    assert len(calls) == 1
