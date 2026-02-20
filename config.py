"""
config.py — Centralised, immutable configuration for the Binance Futures Testnet bot.

Credentials are read exclusively from environment variables or a local .env file
so that secrets never appear in source code.  Every other module imports the
module-level ``config`` singleton.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Optional .env loader (graceful fallback when python-dotenv is absent)
# ---------------------------------------------------------------------------
def _load_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(env_path)
    except ImportError:
        # Manual minimal parser for KEY=VALUE lines
        with env_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Config:
    # ── Credentials (sourced from env) ───────────────────────────────────────
    api_key: str = field(
        default_factory=lambda: os.getenv("BINANCE_TESTNET_API_KEY", "")
    )
    api_secret: str = field(
        default_factory=lambda: os.getenv("BINANCE_TESTNET_API_SECRET", "")
    )

    # ── Testnet endpoints ────────────────────────────────────────────────────
    base_url: str = "https://testnet.binancefuture.com"
    fapi_v1: str = "/fapi/v1"
    fapi_v2: str = "/fapi/v2"

    # ── Behaviour ────────────────────────────────────────────────────────────
    recv_window: int = 5_000   # ms — how long a signed request stays valid
    timeout: int = 10          # seconds — requests.Session timeout
    default_symbol: str = "BTCUSDT"
    default_leverage: int = 10

    # ── Logging ──────────────────────────────────────────────────────────────
    log_dir: Path = field(default_factory=lambda: Path(__file__).parent / "logs")
    log_max_bytes: int = 5 * 1024 * 1024   # 5 MB per log file
    log_backup_count: int = 5

    def validate(self) -> None:
        """Raise :class:`ValueError` if credentials are missing."""
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Missing API credentials.\n"
                "  • Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET\n"
                "    as environment variables, or create a .env file from .env.example."
            )


# Module-level singleton — import this everywhere.
config = Config()
