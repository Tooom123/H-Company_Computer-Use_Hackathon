"""Recover this pilot's desktop channel and enforce an input-only command boundary.

The local bridge rejects shell and filesystem commands before driver invocation.
This is not a sandbox: allowed keyboard/mouse input can still affect whichever
application has focus. A dedicated browser/desktop is needed for app isolation.
"""
from __future__ import annotations

import threading

import httpx
from hai_agents_local.desktop import PyautoguiDesktopBridge
from hai_agents_local.manager import ensure_bridges, serving_bridges, stop_bridges
from hcs_agent.backend import AttemptResult, HBackend, VerifyResult
from hcs_agent.contract import Category, DeclaredResult


class DesktopConnectionError(RuntimeError):
    """The desktop channel cannot safely be reused or opened."""


class RestrictedDesktopBridge(PyautoguiDesktopBridge):
    """Allow only observation and necessary pointer/keyboard/scroll driver calls.

    These are wire-level driver method names, not model tool names (for example,
    run_command rather than run_command_desktop). LocalBridge._dispatch checks
    this allowlist before looking up or invoking any driver attribute. Unknown
    future methods are denied too. Local lifecycle cleanup still calls close()
    directly; the agent cannot request it through the command channel.
    """

    commands = frozenset({
        'platform', 'screenshot_b64', 'get_screen_size', 'get_mouse_position',
        'get_accessibility_tree', 'get_observation_snapshot',
        'get_number_of_pixels_scrolled_per_click',
        'mouse_move_to', 'click', 'double_click',
        'write', 'write_at', 'hotkey', 'tap_key', 'press_key', 'release_key',
        'scroll_by_n_clicks', 'scroll_by_n_pxs', 'scroll_at',
    })


class PilotHBackend(HBackend):
    adapter_revision = 'pilot-bridge-health-v2'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._channel_lock = threading.Lock()

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
        )
        bridge.preflight()
        ensure_bridges([bridge])
        self._desktop_session_id = bridge.session_id
        return bridge.session_id

    @staticmethod
    def _blocked(exc: DesktopConnectionError) -> AttemptResult:
        return AttemptResult(None, 'failed', DeclaredResult(
            outcome='blocked', summary='La connexion au bureau n’a pas pu être établie.',
            blocker=str(exc), blocker_category=Category.environment), error=str(exc))

    def run_attempt(self, *args, **kwargs) -> AttemptResult:
        try:
            return super().run_attempt(*args, **kwargs)
        except DesktopConnectionError as exc:
            return self._blocked(exc)

    def run_guidance(self, *args, **kwargs) -> AttemptResult:
        try:
            return super().run_guidance(*args, **kwargs)
        except DesktopConnectionError as exc:
            return self._blocked(exc)

    def verify(self, *args, **kwargs) -> VerifyResult:
        try:
            return super().verify(*args, **kwargs)
        except DesktopConnectionError as exc:
            return VerifyResult(None, 'failed', error=str(exc))
