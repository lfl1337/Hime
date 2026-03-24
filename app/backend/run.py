"""
Hime backend entry point.

IMPORTANT: Always binds to 127.0.0.1 — never 0.0.0.0.
The host is hardcoded here intentionally; do not make it configurable
via an environment variable, as that would undermine the local-only guarantee.

Port selection:
  - Preferred port comes from settings.port (default 8000, override via .env PORT=XXXX).
  - If that port is busy, scans upward until a free one is found.
  - The chosen port is written to .runtime_port so the frontend can read it
    instead of relying on a hardcoded value.

--data-dir <path>:
  When provided (production Tauri sidecar mode), runtime files (.runtime_port,
  .env, hime.db, logs/) are written to that directory instead of beside run.py.
  Sets HIME_DATA_DIR env var so app.config picks it up before Settings loads.
"""
import argparse
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
    # Fall back to the same AppData path Tauri would pass so .runtime_port
    # ends up somewhere the frontend can find it, not in the temp extract dir.
    _appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    _DATA_DIR = _appdata / "dev.hime.app"
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["HIME_DATA_DIR"] = str(_DATA_DIR)
else:
    _DATA_DIR = Path(__file__).parent  # dev: beside run.py

# Import AFTER HIME_DATA_DIR is set so pydantic-settings reads the right .env
import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402
from app.utils.ports import find_free_port  # noqa: E402

_RUNTIME_PORT_FILE = _DATA_DIR / ".runtime_port"

_HOST = "127.0.0.1"


def _write_runtime_port(port: int) -> None:
    _RUNTIME_PORT_FILE.write_text(str(port), encoding="utf-8")


def _clear_runtime_port() -> None:
    _RUNTIME_PORT_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    port = find_free_port(start=settings.port)

    if port != settings.port:
        print(f"[hime] Port {settings.port} is busy - using {port} instead.", flush=True)

    _write_runtime_port(port)
    print(f"[hime] Backend running on http://{_HOST}:{port}", flush=True)
    print(f"[hime] runtime_port -> {_RUNTIME_PORT_FILE}", flush=True)

    try:
        uvicorn.run(
            "app.main:app",
            host=_HOST,  # Local-only — do not change to 0.0.0.0
            port=port,
            reload=False,  # reload=True conflicts with programmatic port selection
            log_level="info",
        )
    finally:
        _clear_runtime_port()
