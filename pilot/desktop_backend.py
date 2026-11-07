"""Recover only this pilot's expired desktop channel between H sessions."""
from __future__ import annotations

import threading

import httpx
from hai_agents_local.manager import serving_bridges, stop_bridges
from hcs_agent.backend import AttemptResult, HBackend, VerifyResult
from hcs_agent.contract import Category, DeclaredResult


class DesktopConnectionError(RuntimeError):
    """The desktop channel cannot safely be reused or opened."""


class PilotHBackend(HBackend):
    adapter_revision = 'pilot-bridge-health-v1'

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
                return super()._desktop_channel()
            except Exception as exc:
                raise DesktopConnectionError('Impossible d’ouvrir la connexion au bureau. Vérifiez H et les permissions macOS, puis réessayez.') from exc

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
