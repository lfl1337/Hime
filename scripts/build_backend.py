#!/usr/bin/env python
"""Build the Hime backend as a single-file Windows executable for Tauri sidecar."""
import subprocess
from pathlib import Path

ROOT    = Path(__file__).parent.parent          # C:\Projekte\Hime
APP     = ROOT / "app"                          # C:\Projekte\Hime\app
BACKEND = APP / "backend"                       # C:\Projekte\Hime\app\backend
OUT     = APP / "frontend" / "src-tauri" / "binaries"  # …\app\frontend\src-tauri\binaries
OUT.mkdir(parents=True, exist_ok=True)

# Tauri requires the sidecar binary to be named with the target triple.
# On x86-64 Windows the name must be exactly:
#   hime-backend-x86_64-pc-windows-msvc.exe
BINARY_NAME = "hime-backend-x86_64-pc-windows-msvc"

# Install PyInstaller into the uv-managed venv
print("[build] Installing PyInstaller via uv...")
subprocess.run(
    ["uv", "add", "pyinstaller", "--dev"],
    check=True,
    cwd=str(BACKEND),
)

# Run PyInstaller via uv so it uses the correct venv and PATH
print(f"[build] Running PyInstaller (cwd={BACKEND})...")
subprocess.run(
    [
        "uv", "run", "pyinstaller",
        "--onefile",
        "--name", BINARY_NAME,
        "--distpath", str(OUT),
        "--workpath", str(APP / "build" / "pyinstaller"),
        "--specpath",  str(APP / "build"),
        # uvicorn internal imports not auto-detected by PyInstaller
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        # async SQLite driver
        "--hidden-import", "aiosqlite",
        # multipart / form parsing
        "--hidden-import", "multipart",
        "--hidden-import", "email.mime.multipart",
        # app routers (dynamic imports not seen by static analysis)
        "--hidden-import", "app.routers.texts",
        "--hidden-import", "app.routers.translations",
        "--hidden-import", "app.routers.training",
        "--hidden-import", "app.websocket.streaming",
        # pydantic needs full collection due to v2 internals
        "--collect-all", "pydantic",
        "--collect-all", "pydantic_settings",
        str(BACKEND / "run.py"),
    ],
    check=True,
    cwd=str(BACKEND),
)

print(f"\n[build] Binary → {OUT / (BINARY_NAME + '.exe')}")
