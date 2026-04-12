"""VERSION consistency test (W9). After Phase 9 bump, all files must read 2.0.0."""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_app_version_file():
    v = (REPO_ROOT / "app" / "VERSION").read_text(encoding="utf-8").strip()
    assert v == "2.0.0", f"app/VERSION = {v!r}"


def test_backend_pyproject():
    content = (REPO_ROOT / "app" / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert m, "pyproject.toml has no version field"
    assert m.group(1) == "2.0.0", f"pyproject.toml version = {m.group(1)!r}"


def test_frontend_package_json():
    pkg = json.loads((REPO_ROOT / "app" / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == "2.0.0", f"package.json version = {pkg['version']!r}"


def test_tauri_conf():
    conf = json.loads((REPO_ROOT / "app" / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    assert conf.get("version") == "2.0.0", f"tauri.conf.json version = {conf.get('version')!r}"


def test_cargo_toml():
    content = (REPO_ROOT / "app" / "frontend" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert m, "Cargo.toml has no version field"
    assert m.group(1) == "2.0.0", f"Cargo.toml version = {m.group(1)!r}"


def test_backend_main_version():
    content = (REPO_ROOT / "app" / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert '2.0.0' in content, "main.py does not reference version 2.0.0"


def test_sidebar_tsx_version():
    content = (REPO_ROOT / "app" / "frontend" / "src" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    assert 'v2.0.0' in content, "Sidebar.tsx does not display version 2.0.0"
    assert 'v1.1.2' not in content, "Sidebar.tsx still shows old version 1.1.2"


def test_settings_tsx_version():
    content = (REPO_ROOT / "app" / "frontend" / "src" / "views" / "Settings.tsx").read_text(encoding="utf-8")
    assert 'v2.0.0' in content, "Settings.tsx does not display version 2.0.0"
    assert 'v0.7.2' not in content, "Settings.tsx still shows old hardcoded version 0.7.2"
