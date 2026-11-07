"""Bounded Gladia STT callback for the pilot's explicit recordings.

Official API: https://docs.gladia.io/chapters/pre-recorded-stt/quickstart
Upload once, create one French Solaria-3 job, then poll its fixed API endpoint.
No audio, transcript, credential, response body or request headers are logged.
The synchronous callback is intended for pilot.server's worker thread.
"""
from __future__ import annotations

import asyncio
import math
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx


API = 'https://api.gladia.io'
MAX_AUDIO_BYTES = 12 * 1024 * 1024


class GladiaSpeechError(RuntimeError):
    """A user-safe failure message containing no provider response or credential."""


class GladiaSpeech:
    provider = 'Gladia'

    def __init__(self, api_key: str, *, timeout_s: float = 105,
                 poll_interval_s: float = 2,
                 transport: httpx.AsyncBaseTransport | None = None):
        # The injection point is only for offline transport tests, never a URL/key
        # override from an HTTP request or environment variable.
        if not math.isfinite(timeout_s) or not 0 < timeout_s <= 110:
            raise ValueError('Gladia timeout must be between 0 and 110 seconds')
        if not math.isfinite(poll_interval_s) or poll_interval_s < 0:
            raise ValueError('Polling interval must be non-negative')
        self._api_key = api_key.strip()
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s
        self._transport = transport
        self.ready = bool(self._api_key)
        self.message = ('Prêt · Solaria 3 en français ; l’audio est envoyé à Gladia.'
                        if self.ready else 'Clé Gladia absente ; saisie texte disponible.')

    def __call__(self, audio_path: Path, content_type: str) -> dict[str, str]:
        if not self.ready:
            raise GladiaSpeechError(self.message)
        mime = content_type.split(';', 1)[0].strip().lower()
        if mime not in {'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/webm'}:
            raise GladiaSpeechError('Gladia attend un fichier WAV ou WebM audio.')
        path = Path(audio_path)
        try:
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_AUDIO_BYTES:
                raise GladiaSpeechError('Fichier audio absent, vide ou supérieur à 12 Mio.')
            result = asyncio.run(self._bounded_transcription(path, mime))
        except (TimeoutError, httpx.TimeoutException):
            self.message = ('Gladia a dépassé le délai de transcription ; le traitement distant '
                            'peut continuer. La saisie texte reste disponible.')
            raise GladiaSpeechError(self.message) from None
        except httpx.HTTPError:
            self.message = 'Connexion à Gladia interrompue ; vérifiez le réseau puis utilisez la saisie texte.'
            raise GladiaSpeechError(self.message) from None
        except OSError:
            self.message = 'Impossible de lire l’enregistrement local.'
            raise GladiaSpeechError(self.message) from None
        except GladiaSpeechError as exc:
            self.message = str(exc)
            raise
        self.message = 'Prêt · Solaria 3 en français ; l’audio est envoyé à Gladia.'
        return result

    async def _bounded_transcription(self, path: Path, mime: str) -> dict[str, str]:
        # Async cancellation bounds the *whole* upload/job/poll flow, not merely
        # inactivity on each socket read. It leaves room below the 120s IPC limit.
        async with asyncio.timeout(self._timeout_s):
            async with httpx.AsyncClient(
                verify=True, trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(20, connect=10), transport=self._transport,
                headers={'x-gladia-key': self._api_key},
            ) as client:
                suffix = 'webm' if mime == 'audio/webm' else 'wav'
                with path.open('rb') as audio:
                    uploaded = self._response(await client.post(
                        API + '/v2/upload', files={'audio': ('recording.' + suffix, audio, mime)}))
                audio_url = uploaded.get('audio_url')
                if not self._uploaded_url(audio_url):
                    raise GladiaSpeechError('Gladia a renvoyé une adresse audio inattendue.')
                submitted = self._response(await client.post(API + '/v2/pre-recorded', json={
                    'audio_url': audio_url,
                    'model': 'solaria-3',
                    'language_config': {'languages': ['fr'], 'code_switching': False},
                    'diarization': False,
                    'callback': False,
                }))
                try:
                    # Never follow result_url: credentials only reach api.gladia.io.
                    job_id = str(UUID(submitted['id']))
                except (KeyError, TypeError, ValueError, AttributeError):
                    raise GladiaSpeechError('Gladia n’a pas renvoyé un identifiant de transcription valide.') from None
                while True:
                    result = self._response(await client.get(API + '/v2/pre-recorded/' + job_id))
                    status = result.get('status')
                    if status == 'done':
                        transcription = result.get('result')
                        transcription = transcription.get('transcription') if isinstance(transcription, dict) else None
                        transcript = transcription.get('full_transcript') if isinstance(transcription, dict) else None
                        if not isinstance(transcript, str) or not transcript.strip():
                            raise GladiaSpeechError('Aucune parole reconnue ; rapprochez-vous du micro ou saisissez le texte.')
                        if len(transcript) > 20000:
                            raise GladiaSpeechError('La transcription dépasse la limite de texte du pilote.')
                        return {'transcript': transcript.strip(), 'provider': self.provider}
                    if status == 'error':
                        raise GladiaSpeechError('Gladia n’a pas pu transcrire cet enregistrement ; saisie texte disponible.')
                    if status not in {'queued', 'processing'}:
                        raise GladiaSpeechError('Gladia a renvoyé un état de transcription inattendu.')
                    await asyncio.sleep(self._poll_interval_s)

    @staticmethod
    def _uploaded_url(value) -> bool:
        if not isinstance(value, str):
            return False
        try:
            url = urlsplit(value)
            return (url.scheme == 'https' and url.hostname == 'api.gladia.io'
                    and url.port in (None, 443) and url.username is None and url.password is None
                    and url.path.startswith('/file/') and not url.fragment)
        except ValueError:
            return False

    @staticmethod
    def _response(response: httpx.Response) -> dict:
        # Deliberately do not include response.text or raise_for_status(), whose
        # exceptions retain an authenticated request and provider response body.
        if response.status_code in {401, 403}:
            raise GladiaSpeechError('Clé Gladia refusée ; vérifiez la configuration du serveur.')
        if response.status_code == 429:
            raise GladiaSpeechError('Limite ou quota Gladia atteint ; attendez avant un nouvel enregistrement.')
        if response.status_code >= 500:
            raise GladiaSpeechError('Gladia est temporairement indisponible ; saisie texte disponible.')
        if not 200 <= response.status_code < 300:
            raise GladiaSpeechError('Gladia a refusé la requête audio ; saisie texte disponible.')
        try:
            value = response.json()
        except ValueError:
            raise GladiaSpeechError('Réponse Gladia illisible ; saisie texte disponible.') from None
        if not isinstance(value, dict):
            raise GladiaSpeechError('Réponse Gladia inattendue ; saisie texte disponible.')
        return value
