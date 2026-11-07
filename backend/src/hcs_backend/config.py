"""Runtime settings, read from the environment (or backend/.env, git-ignored)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: REPO_ROOT / "runs" / "backend.sqlite3")
    contracts_dir: Path = field(default_factory=lambda: REPO_ROOT / "contracts")
    host: str = "127.0.0.1"
    port: int = 8766
    # Token the agent sends as "Authorization: Bearer <token>" on POST /cases and /events.
    ingest_token: str = ""
    # HTTP Basic credentials for the support dashboard and case read APIs.
    dashboard_user: str = "support"
    dashboard_password: str = ""
    # Jaccard threshold on difficulty keywords for two cases to share a group.
    group_threshold: float = 0.3
    generated_secrets: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv(REPO_ROOT / "backend" / ".env")
        s = cls()
        if v := os.environ.get("HCS_BACKEND_DB"):
            s.db_path = Path(v)
        if v := os.environ.get("HCS_CONTRACTS_DIR"):
            s.contracts_dir = Path(v)
        s.host = os.environ.get("HCS_BACKEND_HOST", s.host)
        s.port = int(os.environ.get("HCS_BACKEND_PORT", s.port))
        s.ingest_token = os.environ.get("HCS_INGEST_TOKEN", "")
        s.dashboard_user = os.environ.get("HCS_DASHBOARD_USER", s.dashboard_user)
        s.dashboard_password = os.environ.get("HCS_DASHBOARD_PASSWORD", "")
        if v := os.environ.get("HCS_GROUP_THRESHOLD"):
            s.group_threshold = float(v)
        s.ensure_secrets()
        return s

    def ensure_secrets(self) -> None:
        """Never run with an empty secret: generate one for this process and say so."""
        if not self.ingest_token:
            self.ingest_token = secrets.token_urlsafe(24)
            self.generated_secrets.append(f"HCS_INGEST_TOKEN={self.ingest_token}")
        if not self.dashboard_password:
            self.dashboard_password = secrets.token_urlsafe(12)
            self.generated_secrets.append(
                f"HCS_DASHBOARD_USER={self.dashboard_user} HCS_DASHBOARD_PASSWORD={self.dashboard_password}"
            )
