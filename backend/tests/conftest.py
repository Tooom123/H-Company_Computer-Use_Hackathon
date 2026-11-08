import pytest


@pytest.fixture(autouse=True)
def _silent_zak(monkeypatch):
    """Tests never speak: Zak's voice (Devin debug announcements) is muted unless a test injects its own."""
    monkeypatch.setenv("HCS_FIX_VOICE", "0")
