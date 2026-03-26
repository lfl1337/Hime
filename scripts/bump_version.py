#!/usr/bin/env python
"""Bump Hime's version across all files from a single source of truth.

Usage:
    python scripts/bump_version.py [major|minor|patch]
    python scripts/bump_version.py set 1.0.0

Updates:
    app/VERSION                              ← source of truth
    app/frontend/src-tauri/tauri.conf.json   ← "version"
    app/frontend/src-tauri/Cargo.toml        ← version =
    app/frontend/package.json                ← "version"
    app/backend/app/main.py                  ← FastAPI() + health endpoint
    app/frontend/src/components/Sidebar.tsx  ← footer label
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent          # C:\Projekte\Hime
APP = ROOT / "app"
FRONTEND = APP / "frontend"
BACKEND = APP / "backend"
VERSION_FILE = APP / "VERSION"


def read_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def parse_version(v: str) -> str:
    parts = v.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"Version must be X.Y.Z — got {v!r}")
    return v


def next_version(current: str, level: str) -> str:
    major, minor, patch = (int(p) for p in current.split("."))
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"level must be major, minor, or patch — got {level!r}")


def sed(path: Path, pattern: str, replacement: str, flags: int = 0) -> None:
    """Regex-replace in a file; warn if the pattern matched nothing."""
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(pattern, replacement, text, flags=flags)
    if n == 0:
        print(f"  WARNING: pattern not matched in {path.relative_to(ROOT)!s}")
        return
    path.write_text(new_text, encoding="utf-8")
    print(f"  updated  {path.relative_to(ROOT)!s}  ({n} replacement{'s' if n > 1 else ''})")


def update_all(old: str, new: str) -> None:
    ov = re.escape(old)

    # 1. VERSION — source of truth
    VERSION_FILE.write_text(new + "\n", encoding="utf-8")
    print(f"  updated  app/VERSION")

    # 2. tauri.conf.json
    sed(
        FRONTEND / "src-tauri" / "tauri.conf.json",
        rf'"version":\s*"{ov}"',
        f'"version": "{new}"',
    )

    # 3. Cargo.toml  (version = "X.Y.Z" at line start)
    sed(
        FRONTEND / "src-tauri" / "Cargo.toml",
        rf'^version\s*=\s*"{ov}"',
        f'version = "{new}"',
        flags=re.MULTILINE,
    )

    # 4. package.json
    sed(
        FRONTEND / "package.json",
        rf'"version":\s*"{ov}"',
        f'"version": "{new}"',
    )

    # 5. backend/app/main.py — FastAPI() kwarg (version="X") and health dict ("version": "X")
    sed(
        BACKEND / "app" / "main.py",
        rf'\bversion="{ov}"',
        f'version="{new}"',
    )
    sed(
        BACKEND / "app" / "main.py",
        rf'"version":\s*"{ov}"',
        f'"version": "{new}"',
    )

    # 6. Sidebar.tsx — footer label
    sed(
        FRONTEND / "src" / "components" / "Sidebar.tsx",
        rf'Hime v{ov}',
        f'Hime v{new}',
    )


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "set":
        old = read_version()
        new = parse_version(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] in ("major", "minor", "patch"):
        old = read_version()
        new = next_version(old, sys.argv[1])
    else:
        print("Usage: python scripts/bump_version.py [major|minor|patch|set X.Y.Z]")
        sys.exit(1)

    label = f"set {new}" if sys.argv[1] == "set" else sys.argv[1]
    print(f"\nBumping version: {old} -> {new}  ({label})\n")
    update_all(old, new)

    print("\nCommitting...")
    subprocess.run(["git", "add", "-A"], check=True, cwd=str(ROOT))
    subprocess.run(
        ["git", "commit", "-m", f"chore: bump version to {new}"],
        check=True,
        cwd=str(ROOT),
    )
    subprocess.run(["git", "tag", f"v{new}"], check=True, cwd=str(ROOT))

    print("\nPushing to GitHub...")
    subprocess.run(["git", "push"], check=True, cwd=str(ROOT))
    subprocess.run(["git", "push", "--tags"], check=True, cwd=str(ROOT))

    print(f"\nDone. Version is now {new}. Tag v{new} pushed.")
    print("Or run:  python scripts/release.py for a full release build.")


if __name__ == "__main__":
    main()
