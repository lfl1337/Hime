"""
Hime backend entry point.

IMPORTANT: Always binds to 127.0.0.1 — never 0.0.0.0.
The host is hardcoded here intentionally; do not make it configurable
via an environment variable, as that would undermine the local-only guarantee.

Port selection:
  - Preferred port comes from settings.port (default 8000, override via .env PORT=XXXX).
  - If that port is busy, scans upward until a free one is found.
  - The chosen port is written to hime-backend.lock (JSON {port, pid}) so
    the frontend can read it instead of relying on a hardcoded value.

--data-dir <path>:
  When provided (production Tauri sidecar mode), runtime files (hime-backend.lock,
  .env, hime.db, logs/) are written to that directory instead of beside run.py.
  Sets HIME_DATA_DIR env var so app.config picks it up before Settings loads.
"""
import argparse
import json
import os
import sys
from pathlib import Path

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--data-dir", default=None)
_args, _ = _parser.parse_known_args()

if _args.data_dir:
    # Tauri sidecar mode: use the directory Tauri chose (%APPDATA%\dev.hime.app)
    _DATA_DIR = Path(_args.data_dir)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["HIME_DATA_DIR"] = str(_DATA_DIR)
elif getattr(sys, "frozen", False):
    # Frozen PyInstaller exe run without --data-dir (e.g. manual testing).
    # Fall back to the same AppData path Tauri would pass so hime-backend.lock
    # ends up somewhere the frontend can find it, not in the temp extract dir.
    _appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    _DATA_DIR = _appdata / "dev.hime.app"
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["HIME_DATA_DIR"] = str(_DATA_DIR)
else:
    _DATA_DIR = Path(__file__).parent  # dev: beside run.py

# Import AFTER HIME_DATA_DIR is set so pydantic-settings reads the right .env
from app.logger import setup_logging  # noqa: E402

_LOG_DIR = _DATA_DIR / "logs"
setup_logging(_LOG_DIR, dev=not bool(_args.data_dir))

import logging as _logging  # noqa: E402
import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402
from app.utils.ports import find_free_port  # noqa: E402

_log = _logging.getLogger("hime")

_BACKEND_LOCK_FILE = _DATA_DIR / "hime-backend.lock"

_HOST = "127.0.0.1"


def _write_backend_lock(port: int) -> None:
    _BACKEND_LOCK_FILE.write_text(
        json.dumps({"port": port, "pid": os.getpid()}),
        encoding="utf-8",
    )


def _clear_backend_lock() -> None:
    _BACKEND_LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    from app.main import app as _app  # noqa: E402 — needed for version

    port = find_free_port(start=settings.port)

    _write_backend_lock(port)

    _log.info("Hime Backend v%s starting...", _app.version)
    _log.info("  Data dir    : %s", _DATA_DIR)
    _log.info("  Models path : %s", settings.models_base_path)
    _log.info("  LoRA path   : %s", settings.lora_path)
    _log.info("  Watch folder: (from DB setting)")
    _log.info("  Log file    : %s", _LOG_DIR / "hime-backend.log")
    if port != settings.port:
        _log.warning("Port %s busy — using %s instead", settings.port, port)
    _log.info("Listening on http://%s:%s", _HOST, port)
    _log.debug("backend_lock -> %s", _BACKEND_LOCK_FILE)

    try:
        uvicorn.run(
            "app.main:app",
            host=_HOST,  # Local-only — do not change to 0.0.0.0
            port=port,
            reload=False,  # reload=True conflicts with programmatic port selection
            log_level="info",
        )
    finally:
        _clear_backend_lock()
