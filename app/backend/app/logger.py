"""Centralized logging for the Hime backend."""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

_RESET  = "\033[0m"
_COLORS = {
    "DEBUG":    "\033[90m",   # dark grey
    "INFO":     "\033[97m",   # bright white
    "WARNING":  "\033[93m",   # yellow
    "ERROR":    "\033[91m",   # red
    "CRITICAL": "\033[95m",   # magenta
}

_FMT   = "[%(asctime)s] %(levelname)-8s %(name)-20s %(message)s"
_DFMT  = "%Y-%m-%d %H:%M:%S"


class _ColourFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        colour = _COLORS.get(record.levelname, _RESET)
        record.levelname = f"{colour}{record.levelname:<8}{_RESET}"
        return super().format(record)


def setup_logging(log_dir: Path, *, dev: bool = True) -> None:
    """Configure root logger. Call once at process start (in run.py)."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. uvicorn reload worker)
    root.setLevel(logging.DEBUG)

    # Console — INFO+ in dev, WARNING+ in release
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO if dev else logging.WARNING)
    ch.setFormatter(_ColourFormatter(_FMT, datefmt=_DFMT))
    root.addHandler(ch)

    # File — INFO+ by default (DEBUG+ only when DEBUG=true), rotating 5 MB × 3 backups
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "hime-backend.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_level = logging.DEBUG if os.getenv("DEBUG", "").lower() == "true" else logging.INFO
    fh.setLevel(file_level)
    fh.setFormatter(logging.Formatter(_FMT, datefmt=_DFMT))
    root.addHandler(fh)

    # Silence extremely verbose third-party loggers
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("hime.requests").setLevel(logging.WARNING)
