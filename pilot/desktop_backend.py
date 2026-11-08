"""Recover this pilot's desktop channel and guard every remote desktop command.

The local bridge rejects shell/filesystem commands and requires Google Chrome
to be the macOS frontmost app before each observation or input. This is not a
sandbox: it does not isolate Chrome tabs, other windows in a full-screen capture,
or focus changes between the check and execution. Use a dedicated demo desktop.
"""
from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
from hai_agents_local.desktop import PyautoguiDesktopBridge
from hai_agents_local.manager import ensure_bridges, serving_bridges, stop_bridges
from hcs_agent.backend import AttemptResult, HBackend, VerifyResult
from hcs_agent.contract import Category, DeclaredResult


class DesktopConnectionError(RuntimeError):
    """The desktop channel cannot safely be reused or opened."""


def _macos_frontmost_bundle_id() -> str | None:
    """Read the active app identity without activating or otherwise controlling it."""
    if sys.platform != 'darwin':
        return None
    from AppKit import NSWorkspace

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.bundleIdentifier() if app is not None else None


def _chrome_is_frontmost(reader: Callable[[], str | None]) -> bool:
    """Fail closed without disclosing native lookup errors or private app names."""
    try:
        return sys.platform == 'darwin' and reader() == 'com.google.Chrome'
    except Exception:
        return False


class RestrictedDesktopBridge(PyautoguiDesktopBridge):
    """Allow only observation and necessary pointer/keyboard/scroll driver calls.

    These are wire-level driver method names, not model tool names (for example,
    run_command rather than run_command_desktop). LocalBridge._dispatch checks
    this allowlist before looking up or invoking any driver attribute. Unknown
    future methods are denied too. Local lifecycle cleanup still calls close()
    directly; the agent cannot request it through the command channel.

    Every allowed command, including screenshots, accessibility trees and bundled
    observations, also requires Chrome in front. Missing/failed macOS identity
    checks fail closed before driver attribute access. This application check
    does not establish the active tab's origin or hide other visible windows.
    """

    foreground_error = 'Desktop command blocked: Google Chrome must be active on macOS.'

    commands = frozenset({
        'platform', 'screenshot_b64', 'get_screen_size', 'get_mouse_position',
        'get_accessibility_tree', 'get_observation_snapshot',
        'get_number_of_pixels_scrolled_per_click',
        'mouse_move_to', 'click', 'double_click',
        # No split key-down/key-up: a focus loss must not strand a held key.
        'write', 'write_at', 'hotkey', 'tap_key',
        'scroll_by_n_clicks', 'scroll_by_n_pxs', 'scroll_at',
    })

    def __init__(self, *args, frontmost_bundle_id: Callable[[], str | None] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._frontmost_bundle_id = frontmost_bundle_id or _macos_frontmost_bundle_id

    def _dispatch(self, name, args):
        # Preserve the v2 allowlist before touching either the OS or the driver.
        if name not in self.commands:
            return None, f"command {name!r} is not supported by this {self.environment_kind} bridge"
        if not _chrome_is_frontmost(self._frontmost_bundle_id):
            return None, self.foreground_error
        return super()._dispatch(name, args)


class PilotHBackend(HBackend):
    adapter_revision = 'pilot-bridge-health-v4'

    def __init__(self, *, frontmost_bundle_id: Callable[[], str | None] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._frontmost_bundle_id = frontmost_bundle_id or _macos_frontmost_bundle_id
        self._channel_lock = threading.Lock()

    def _require_chrome(self) -> None:
        if not _chrome_is_frontmost(self._frontmost_bundle_id):
            raise DesktopConnectionError(RestrictedDesktopBridge.foreground_error)

    def screenshot(self, path: Path) -> Path | None:
        # Runner snapshots are optional: None means no evidence file, not a crash.
        # Check before the parent can instantiate a driver or capture any pixels.
        if not _chrome_is_frontmost(self._frontmost_bundle_id):
            return None
        return super().screenshot(path)

    def _visual_check(self, method: str, expected: str) -> tuple[bool, str]:
        """Bypass the upstream fail-open wrapper, while retaining real grounding.

        A missing verifier is inconclusive, never an observed match. The current
        GUIDE runner interprets a non-empty effect description without the app
        name as another app being in front (and keeps waiting). For unavailable
        effect checks, leave that description empty and retain an explicit
        diagnostic separately. False makes its fast verifier fall back to the
        full verifier instead of manufacturing successful postconditions.
        """
        try:
            self._require_chrome()
            result = getattr(self._grounding(), method)(expected)
            self._require_chrome()
            if (not isinstance(result, tuple) or len(result) != 2
                    or type(result[0]) is not bool or not isinstance(result[1], str)
                    or not result[1].strip()):
                raise ValueError('Unusable visual check result')
        except Exception:
            message = 'Vérification visuelle indisponible : résultat inconclusif, aucune réussite confirmée.'
            # Never forward raw capture/network exceptions to a recorded trace.
            self.last_visual_check = {'check': method, 'status': 'unavailable', 'message': message}
            return False, '' if method == 'effect_visible' else message
        self.last_visual_check = {'check': method, 'status': 'observed', 'matched': result[0]}
        return result

    def effect_visible(self, expected: str) -> tuple[bool, str]:
        return self._visual_check('effect_visible', expected)

    def screen_matches(self, expected: str) -> tuple[bool, str]:
        return self._visual_check('screen_matches', expected)

    def _close_orphans(self) -> None:
        # The inherited cleanup scans every session sharing the team's API key.
        # This adapter may stop only its own cached desktop bridge instead.
        return None

    def _channel_status(self, sid: str) -> str:
        wrapper = self._client._client_wrapper
        try:
            with httpx.Client(timeout=10, follow_redirects=False,
                              headers={'Authorization': f'Bearer {wrapper._api_key}'}) as client:
                response = client.get(f'{wrapper.get_base_url().rstrip("/")}/api/v1/trajectories/{sid}')
            if response.status_code == 404:
                return 'missing'
            if response.status_code != 200:
                raise DesktopConnectionError(
                    f'Vérification de la connexion au bureau refusée (HTTP {response.status_code}). Réessayez après rétablissement de H.')
            data = response.json()
        except httpx.RequestError as exc:
            raise DesktopConnectionError('Connexion à H indisponible ; le bureau ne peut pas être vérifié.') from exc
        except ValueError as exc:
            raise DesktopConnectionError('Réponse de H illisible pendant la vérification du bureau.') from exc
        status = data.get('status') if isinstance(data, dict) else None
        if not isinstance(status, str) or status not in {'pending', 'running', 'idle', 'completed', 'failed', 'timed_out', 'interrupted'}:
            raise DesktopConnectionError('Statut de connexion au bureau inattendu ; intervention suspendue.')
        return status

    def _desktop_channel(self) -> str:
        with self._channel_lock:
            sid = self._desktop_session_id
            if sid is not None:
                status = self._channel_status(sid)
                if status in {'pending', 'running', 'idle'} and sid in serving_bridges([sid]):
                    return sid
                try:
                    # Never clean up another teammate's session or all local bridges.
                    stop_bridges([sid])
                except Exception as exc:
                    raise DesktopConnectionError('Impossible de confirmer l’arrêt de notre ancienne connexion au bureau.') from exc
                self._desktop_session_id = None
            try:
                return self._open_desktop_channel()
            except Exception as exc:
                raise DesktopConnectionError('Impossible d’ouvrir la connexion au bureau. Vérifiez H et les permissions macOS, puis réessayez.') from exc

    def _open_desktop_channel(self) -> str:
        """Create our restricted bridge; never fall back to the permissive SDK bridge."""
        wrapper = self._client._client_wrapper
        bridge = RestrictedDesktopBridge(
            'user-mac', api_key=wrapper._api_key, base_url=wrapper.get_base_url(),
            max_width=self.screenshot_max_width,
            frontmost_bundle_id=self._frontmost_bundle_id,
        )
        bridge.preflight()
        ensure_bridges([bridge])
        self._desktop_session_id = bridge.session_id
        return bridge.session_id

    @staticmethod
    def _blocked(exc: DesktopConnectionError) -> AttemptResult:
        return AttemptResult(None, 'failed', DeclaredResult(
            outcome='blocked', summary='L’intervention au bureau est bloquée.',
            blocker=str(exc), blocker_category=Category.environment), error=str(exc))

    def run_attempt(self, *args, **kwargs) -> AttemptResult:
        try:
            self._require_chrome()
            return super().run_attempt(*args, **kwargs)
        except DesktopConnectionError as exc:
            return self._blocked(exc)

    def run_guidance(self, *args, **kwargs) -> AttemptResult:
        try:
            self._require_chrome()
            return super().run_guidance(*args, **kwargs)
        except DesktopConnectionError as exc:
            return self._blocked(exc)

    def verify(self, *args, **kwargs) -> VerifyResult:
        try:
            self._require_chrome()
            result = super().verify(*args, **kwargs)
            diagnostic = getattr(self, 'last_visual_check', {})
            if (isinstance(result, VerifyResult) and not result.checks
                    and diagnostic.get('status') == 'unavailable'):
                result.observed = (result.observed + ' ' + diagnostic['message']).strip()
            return result
        except DesktopConnectionError as exc:
            return VerifyResult(None, 'failed', error=str(exc))
