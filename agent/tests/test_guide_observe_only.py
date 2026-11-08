"""Observe-only GUIDE boundaries, entirely offline: no screen or H API access."""

import threading
from types import SimpleNamespace

import pytest

from hcs_agent.backend import AttemptResult, HBackend, MockBackend, ReadOnlyDesktopBridge
from hcs_agent.contract import ApproveCommand, CaseStatus, DeclaredResult, GuidanceStep, InterventionRequest, Mode, NextCommand, State
from hcs_agent.procedures import ProcedureRegistry
from hcs_agent.runner import Intervention


@pytest.mark.parametrize("command", ["click", "write", "write_at", "hotkey", "mouse_move_to", "scroll_at",
                                    "run_command", "read_file", "write_file", "close", "execute_script", "new_method"])
def test_bridge_rejects_input_and_unknown_commands_before_driver_access(command):
    bridge = ReadOnlyDesktopBridge(api_key="offline-placeholder")
    class Untouchable:
        def __getattribute__(self, name):
            pytest.fail("Rejected command touched the driver")
    bridge._driver = Untouchable()
    value, error = bridge._dispatch(command, {"text": "private-marker"})
    assert value is None and "disabled" in error
    assert "private-marker" not in error


@pytest.mark.parametrize("command,result", [("screenshot_b64", "image"), ("platform", "darwin"),
                                            ("get_screen_size", (1280, 832))])
def test_bridge_serves_only_known_observation_commands(command, result):
    bridge = ReadOnlyDesktopBridge(api_key="offline-placeholder")
    bridge._driver = SimpleNamespace(**{command: lambda: result})
    value, error = bridge._dispatch(command, {})
    assert error is None
    assert value == (list(result) if isinstance(result, tuple) else result)
    assert bridge._dispatch(command, {"path": "private-marker"})[0] is None


def test_bridge_driver_error_is_generic_and_never_logged(caplog):
    bridge = ReadOnlyDesktopBridge(api_key="offline-placeholder")
    def broken():
        raise RuntimeError("private-marker")
    bridge._driver = SimpleNamespace(screenshot_b64=broken)
    value, error = bridge._dispatch("screenshot_b64", {})
    assert value is None and "unavailable" in error
    assert "private-marker" not in error + caplog.text


def test_every_other_installed_sdk_driver_method_is_denied():
    from hai_drivers.desktop.interface import DesktopDriverInterface
    bridge = ReadOnlyDesktopBridge(api_key="offline-placeholder")
    # No driver installed: any unintended dispatch would raise AttributeError.
    for name in dir(DesktopDriverInterface):
        if not name.startswith("_") and name not in bridge.commands:
            assert "disabled" in bridge._dispatch(name, {})[1]


def test_observe_backend_freezes_permission_skips_orphans_and_refuses_actor(monkeypatch):
    import hai_agents
    monkeypatch.setenv("HCS_GUIDE_OBSERVE_ONLY", "1")
    monkeypatch.delenv("HCS_AUTO_CLEANUP", raising=False)
    monkeypatch.setattr(hai_agents, "Client", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(HBackend, "_close_orphans", lambda _: pytest.fail("Foreign cleanup"))
    backend = HBackend(api_key="offline-placeholder")
    monkeypatch.delenv("HCS_GUIDE_OBSERVE_ONLY")
    assert backend.observe_only
    result = backend.run_attempt(None, "task", 1, lambda _: None, threading.Event())
    assert result.declared.outcome == "blocked" and result.h_session_id is None
    assert backend.verify(None, None, threading.Event()).status == "inconclusive"


def test_agent_spec_uses_guarded_channel_without_shell(monkeypatch):
    backend = object.__new__(HBackend)
    backend.observe_only, backend.model, backend.screenshot_max_width = True, "holo4", 1280
    monkeypatch.setattr(backend, "_desktop_channel", lambda: "owned-channel")
    spec = backend._agent_spec("guide", "Explain")
    assert spec["environments"][0]["shell"] is False
    assert spec["environments"][0]["session_id"] == "owned-channel"
    assert "Never click" in spec["instructions"]


def test_desktop_channel_installs_read_only_bridge(monkeypatch):
    import hai_agents_local.manager as manager
    backend = object.__new__(HBackend)
    backend.observe_only, backend.screenshot_max_width, backend._desktop_session_id = True, 1280, None
    backend._client = SimpleNamespace(_client_wrapper=SimpleNamespace(_api_key="offline-placeholder", get_base_url=lambda: "https://example.invalid"))
    monkeypatch.setattr(ReadOnlyDesktopBridge, "preflight", lambda _: None)
    seen = []
    monkeypatch.setattr(manager, "ensure_bridges", lambda bridges: seen.extend(bridges))
    assert backend._desktop_channel() == seen[0].session_id
    assert isinstance(seen[0], ReadOnlyDesktopBridge)


@pytest.mark.parametrize("method", ["effect_visible", "screen_matches"])
@pytest.mark.parametrize("bad", [None, (True,), (True, ""), (1, "observed"), (True, None), RuntimeError("private-marker")])
def test_base_backend_visual_checks_fail_closed(monkeypatch, method, bad):
    backend = object.__new__(HBackend)
    backend.use_a11y = False  # exercise malformed visual responses without reading the real browser tree
    def check(_):
        if isinstance(bad, Exception):
            raise bad
        return bad
    monkeypatch.setattr(backend, "_grounding", lambda: SimpleNamespace(**{method: check}))
    assert getattr(backend, method)("expected") == (False, "")
    assert backend.last_visual_check["status"] == "unavailable"
    assert "private-marker" not in str(backend.last_visual_check)


def _request(autonomy=0):
    return InterventionRequest(software="odoo", goal="Help", mode=Mode.guide, autonomy=autonomy,
                               procedure_id="odoo_crm_followup_activity",
                               parameters={"opportunity": "Acme", "due_date": "2026-11-14"})


def test_autonomy_zero_uncertain_verification_never_starts_actor_verifier(tmp_path, monkeypatch):
    backend = MockBackend(step_delay_s=0)
    monkeypatch.setattr(backend, "verify", lambda *a: pytest.fail("Autonomous verification"))
    monkeypatch.setattr(backend, "run_attempt", lambda *a: pytest.fail("Takeover"))
    monkeypatch.setattr(backend, "effect_visible", lambda _: (False, ""))
    runner = Intervention(_request(), backend, ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    monkeypatch.setattr(runner, "_scripted_guide", lambda bound: AttemptResult(None, "completed", DeclaredResult(outcome="done")))
    runner.start()
    runner.approve(ApproveCommand())
    runner.wait(3)
    assert runner.report.status is CaseStatus.escalated
    assert not runner.report.verification.satisfied
    assert not runner.report.verification.performed
    assert "does not confirm" in runner.report.verification.observed
    assert not runner.takeover


def test_dynamic_guide_still_waits_for_human_and_cannot_raise_autonomy(tmp_path, monkeypatch):
    monkeypatch.setenv("HCS_GUIDE_OBSERVE_ONLY", "1")
    backend = MockBackend(step_delay_s=0)
    monkeypatch.setattr(backend, "run_attempt", lambda *a: pytest.fail("Takeover"))
    monkeypatch.setattr(backend, "verify", lambda *a: pytest.fail("Autonomous verifier"))
    request = _request(autonomy=2).model_copy(update={"mode": Mode.act})
    events, reached = [], threading.Event()
    runner = Intervention(request, backend, ProcedureRegistry(), events.append, tmp_path, uplink=False)
    monkeypatch.setattr(type(runner._bound), "guide_script", lambda _: [])
    def guidance(bound, task, on_step, on_guidance, stop, on_lookup):
        reached.set()
        reply = on_guidance(GuidanceStep(index=1, instruction="Open the visible tab"))
        assert reply == (True, None)
        return AttemptResult(None, "completed", DeclaredResult(outcome="done"))
    monkeypatch.setattr(backend, "run_guidance", guidance)
    # This exercises the Agents fallback, independently of the new AX planner path.
    monkeypatch.setattr(backend, "page_catalogue", lambda *args: None)
    runner.start()
    assert runner.request.mode is Mode.guide and runner.autonomy == 0
    runner.approve(ApproveCommand())
    assert reached.wait(2)
    for _ in range(100):
        runner.wait(.01)
        if runner.state is State.awaiting_user:
            break
    runner.set_autonomy(2)
    assert runner.autonomy == 0 and not runner._user_event.is_set()
    runner.next(NextCommand(done=True))
    runner.wait(3)
    assert runner.report.status is CaseStatus.resolved and not runner.takeover


def test_missing_visual_check_never_confirms_step():
    runner = object.__new__(Intervention)
    runner.backend = SimpleNamespace()
    assert runner._screen_shows("expected") == "no"
    assert runner._ensure_screen(SimpleNamespace(expected_screen="expected")) is False


def test_fast_verification_keeps_evidence_without_an_invented_h_session(tmp_path, monkeypatch):
    backend = MockBackend(step_delay_s=0)
    observed = "Odoo visibly confirms the requested activity and due date."
    monkeypatch.setattr(backend, "effect_visible", lambda _: (True, observed))
    monkeypatch.setattr(backend, "verify", lambda *a: pytest.fail("Unexpected autonomous verifier"))
    runner = Intervention(_request(), backend, ProcedureRegistry(), lambda _: None, tmp_path, uplink=False)
    owned_id = "00000000-0000-4000-8000-000000000000"  # offline fixture, never sent to H
    monkeypatch.setattr(runner, "_scripted_guide", lambda bound: AttemptResult(
        owned_id, "completed", DeclaredResult(outcome="done")))
    runner.start()
    runner.approve(ApproveCommand())
    runner.wait(3)
    report = runner.report
    assert report.status is CaseStatus.resolved
    assert report.h_session_ids == [owned_id]
    assert report.verification.performed and report.verification.satisfied
    assert set(report.verification.checks) == set(runner._bound.checks)
    assert observed in report.verification.observed
    assert report.verification.evidence_refs == []
    for key in runner._bound.checks:
        assert any(step.summary.startswith(f"fast check {key}: yes") for step in report.steps)
