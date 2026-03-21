#!/usr/bin/env python
"""Full release: bump version, build installer, push to git.

Usage:
    python scripts/release.py [major|minor|patch]

Steps:
    1. python scripts/bump_version.py <level>
    2. build.bat  (PyInstaller + Tauri NSIS)
    3. git push && git push --tags
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
APP = ROOT / "app"
VERSION_FILE = APP / "VERSION"


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("major", "minor", "patch"):
        print("Usage: python scripts/release.py [major|minor|patch]")
        sys.exit(1)

    level = sys.argv[1]

    print(f"\n=== Step 1/3: Bumping version ({level}) ===")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bump_version.py"), level],
        check=True,
    )

    new = VERSION_FILE.read_text(encoding="utf-8").strip()

    print(f"\n=== Step 2/3: Building Hime v{new} ===")
    subprocess.run(
        str(APP / "build.bat"),
        check=True,
        shell=True,
        cwd=str(APP),
    )

    print(f"\n=== Step 3/3: Pushing to git ===")
    subprocess.run(["git", "push"], check=True, cwd=str(ROOT))
    subprocess.run(["git", "push", "--tags"], check=True, cwd=str(ROOT))

    installer = (
        APP / "frontend" / "src-tauri" / "target" / "release" / "bundle" / "nsis"
        / f"Hime_{new}_x64-setup.exe"
    )
    print(f"\nReleased Hime v{new} — installer at {installer}")


if __name__ == "__main__":
    main()
