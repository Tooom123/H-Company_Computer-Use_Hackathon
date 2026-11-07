"""Local-only transcription; the model must have been downloaded beforehand."""
from pathlib import Path
from threading import Lock
import time
import wave


class LocalSpeech:
    provider = 'Whisper base · local Mac'

    def __init__(self, model: Path):
        self.model = model
        self.ready = (model / 'config.json').is_file() and (model / 'weights.npz').is_file()
        self.message = 'Audio traité sur ce Mac.' if self.ready else 'Modèle local absent : terminer le téléchargement avant de parler.'
        self._lock = Lock()

    def __call__(self, audio_path: Path, content_type: str):
        if not self.ready:
            raise RuntimeError(self.message)
        import mlx_whisper
        import numpy as np
        started = time.perf_counter()
        with self._lock:
            # The renderer provides PCM16 mono WAV at 16 kHz. Decode it directly:
            # a system ffmpeg install is neither needed nor trusted for this path.
            if content_type in {'audio/wav', 'audio/x-wav'}:
                with wave.open(str(audio_path), 'rb') as source:
                    if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                        raise ValueError('Audio attendu : WAV mono PCM16 à 16 kHz.')
                    audio = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32) / 32768.0
            else:
                from mlx_whisper.audio import load_audio
                audio = load_audio(str(audio_path))
            if not len(audio) or float(np.sqrt(np.mean(audio ** 2))) < 0.002:
                raise ValueError('Aucune voix suffisamment audible. Rapprochez-vous du microphone et recommencez.')
            result = mlx_whisper.transcribe(
                audio, path_or_hf_repo=str(self.model), language='fr',
                temperature=0, condition_on_previous_text=False, verbose=None,
                initial_prompt='Odoo. Holo Gingembre. Holo Pomme. Holo Hibiscus. Fournisseur Holo Démo.',
            )
        text = str(result.get('text', '')).strip()
        if not text:
            raise ValueError('Aucune parole reconnue. Recommencez ou saisissez votre demande.')
        return {'transcript': text, 'provider': self.provider, 'latency_ms': round((time.perf_counter() - started) * 1000)}
