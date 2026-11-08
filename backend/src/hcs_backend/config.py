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
    vision_evidence_dir: Path | None = None  # opt-in local payload viewer; not a screenshot upload service
    # Token the agent sends as "Authorization: Bearer <token>" on POST /cases and /events.
    ingest_token: str = ""
    # HTTP Basic credentials for the support dashboard and case read APIs.
    dashboard_user: str = "support"
    dashboard_password: str = ""
    # Jaccard threshold on difficulty keywords for two cases to share a group.
    group_threshold: float = 0.3
    # Stripe Checkout (test mode) for the landing paywall
    stripe_secret_key: str = ""
    landing_url: str = "http://127.0.0.1:5173"
    # Auto-fix with Devin (Cognition): allowlist "Software name=owner/repo; ..."
    fix_repos: str = ""
    fix_auto: bool = False
    fix_provider: str = "auto"         # auto (devin if a key is set, else mock) | devin | mock
    devin_api_key: str = ""
    devin_org_id: str = ""
    devin_api_base: str = "https://api.devin.ai"
    fix_max_acu: int = 5
    fix_poll_s: float = 30.0
    fix_mock_run_s: float = 6.0
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
        s.stripe_secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
        s.landing_url = os.environ.get("HCS_LANDING_URL", s.landing_url)
        s.fix_repos = os.environ.get("HCS_FIX_REPOS", "")
        s.fix_auto = os.environ.get("HCS_FIX_AUTO", "0") == "1"
        s.fix_provider = os.environ.get("HCS_FIX_PROVIDER", s.fix_provider)
        s.devin_api_key = os.environ.get("DEVIN_API_KEY", "")
        s.devin_org_id = os.environ.get("DEVIN_ORG_ID", "")
        s.devin_api_base = os.environ.get("DEVIN_API_BASE", s.devin_api_base)
        if v := os.environ.get("HCS_FIX_MAX_ACU"):
            s.fix_max_acu = int(v)
        if v := os.environ.get("HCS_FIX_POLL_S"):
            s.fix_poll_s = float(v)
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
