"""
logger.py — Two-channel structured logging.

Console  →  INFO and above, ANSI-coloured level tag, human-readable.
File     →  DEBUG and above, plain text, rotating (5 × 5 MB), machine-readable.

Usage:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Server started")
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import config as _cfg

# Shared format strings
_FILE_FMT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class _AnsiFormatter(logging.Formatter):
    """Injects ANSI colour codes around the level-name token only."""

    _COL = {
        logging.DEBUG:    "\033[36m",   # cyan
        logging.INFO:     "\033[32m",   # green
        logging.WARNING:  "\033[33m",   # yellow
        logging.ERROR:    "\033[31m",   # red
        logging.CRITICAL: "\033[1;35m", # bold magenta
    }
    _RST = "\033[0m"
    # Console format keeps logger name short for readability
    _CONSOLE_FMT = "%(asctime)s │ {col}%(levelname)-8s{rst} │ %(name)-18s │ %(message)s"

    def __init__(self) -> None:
        super().__init__(datefmt=_DATE_FMT)

    def format(self, record: logging.LogRecord) -> str:
        col = self._COL.get(record.levelno, "")
        self._style._fmt = self._CONSOLE_FMT.format(col=col, rst=self._RST)  # type: ignore[attr-defined]
        return super().format(record)


def get_logger(name: str = "trading_bot") -> logging.Logger:
    """
    Return a named :class:`logging.Logger`.

    Handlers are attached only on the first call; subsequent calls with the
    same *name* return the cached, already-configured logger.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── Console ─────────────────────────────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_AnsiFormatter())
    logger.addHandler(ch)

    # ── Rotating file ────────────────────────────────────────────────────────
    _cfg.log_dir.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(
        _cfg.log_dir / "bot.log",
        maxBytes=_cfg.log_max_bytes,
        backupCount=_cfg.log_backup_count,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FILE_FMT, _DATE_FMT))
    logger.addHandler(fh)

    logger.propagate = False
    return logger
