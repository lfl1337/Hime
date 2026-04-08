"""
Post-disk-migration validator.

Run this after moving the project to a new disk to confirm everything still
resolves correctly. Reports OK / WARN / FAIL per check.

Set HIME_SKIP_TRAINING_PROBE=1 if you want to skip the train_with_resume
dry-run check (e.g., during active training when you want to run the validator
but not touch the training subsystem).

Usage:
    python scripts/verify_migration.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the backend importable without installing it
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT") or SCRIPT_DIR.parent)
sys.path.insert(0, str(PROJECT_ROOT / "app" / "backend"))


_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_RESET = "\033[0m"

_results: list[tuple[str, str, str]] = []  # (level, label, message)


def _ok(label: str, msg: str = "") -> None:
    _results.append(("OK", label, msg))


def _warn(label: str, msg: str = "") -> None:
    _results.append(("WARN", label, msg))


def _fail(label: str, msg: str = "") -> None:
    _results.append(("FAIL", label, msg))


def check_env_vars() -> None:
    expected = [
        "HIME_PROJECT_ROOT",
        "HIME_DATA_DIR",
        "HIME_MODELS_DIR",
        "HIME_LOGS_DIR",
        "HIME_EPUB_WATCH_DIR",
        "HIME_TRAINING_DATA_DIR",
        "HIME_SCRIPTS_DIR",
        "HIME_EMBEDDINGS_DIR",
        "HIME_RAG_DIR",
    ]
    for var in expected:
        val = os.environ.get(var)
        if val is None:
            _warn(f"env:{var}", "(unset - using default)")
        else:
            _ok(f"env:{var}", val)


def check_paths_module() -> None:
    try:
        from app.core import paths
    except Exception as e:  # noqa: BLE001
        _fail("import:app.core.paths", str(e))
        return
    _ok("import:app.core.paths", str(paths.PROJECT_ROOT))

    targets = [
        ("PROJECT_ROOT", paths.PROJECT_ROOT),
        ("DATA_DIR", paths.DATA_DIR),
        ("MODELS_DIR", paths.MODELS_DIR),
        ("LOGS_DIR", paths.LOGS_DIR),
        ("EPUB_WATCH_DIR", paths.EPUB_WATCH_DIR),
        ("TRAINING_DATA_DIR", paths.TRAINING_DATA_DIR),
        ("SCRIPTS_DIR", paths.SCRIPTS_DIR),
    ]
    if hasattr(paths, "EMBEDDINGS_DIR"):
        targets.append(("EMBEDDINGS_DIR", paths.EMBEDDINGS_DIR))
    if hasattr(paths, "RAG_DIR"):
        targets.append(("RAG_DIR", paths.RAG_DIR))

    for name, p in targets:
        if p.exists():
            _ok(f"path:{name}", str(p))
        else:
            # Logs, RAG, embeddings, and training data may not exist yet - that's OK
            if name in {"LOGS_DIR", "RAG_DIR", "EMBEDDINGS_DIR", "TRAINING_DATA_DIR"}:
                _warn(f"path:{name}", f"{p} (missing - will be created on first use)")
            else:
                _fail(f"path:{name}", f"{p} (missing)")


def check_training_config() -> None:
    cfg_path = PROJECT_ROOT / "scripts" / "training_config.json"
    if not cfg_path.exists():
        _fail("training_config.json", "missing")
        return
    try:
        import json
        with cfg_path.open(encoding="utf-8") as f:
            data = json.load(f)
        _ok("training_config.json", f"{len(data)} top-level keys")
    except Exception as e:  # noqa: BLE001
        _fail("training_config.json", f"parse error: {e}")


def check_train_with_resume_dry_run() -> None:
    if os.environ.get("HIME_SKIP_TRAINING_PROBE") == "1":
        _warn("train_with_resume.py --dry-run", "skipped (HIME_SKIP_TRAINING_PROBE=1)")
        return
    script = PROJECT_ROOT / "scripts" / "train_with_resume.py"
    if not script.exists():
        _warn("train_with_resume.py", "not present (WS1 may not have merged yet)")
        return
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--model-name", "Qwen2.5-32B-Instruct", "--dry-run", "--no-prompt"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            _ok("train_with_resume.py --dry-run", "exit 0")
        else:
            _fail("train_with_resume.py --dry-run", f"exit {result.returncode}: {result.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        _fail("train_with_resume.py --dry-run", "timeout")
    except Exception as e:  # noqa: BLE001
        _fail("train_with_resume.py --dry-run", str(e))


def check_no_hardcoded_paths_in_scripts() -> None:
    bad = []
    scripts_dir = PROJECT_ROOT / "scripts"
    if not scripts_dir.exists():
        _fail("scripts/", "directory missing")
        return
    for py_file in scripts_dir.glob("*.py"):
        if py_file.name == "verify_migration.py":
            continue  # self-reference: we scan for the literal, of course we contain it
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        # Strip line comments before checking - build_backend.py and bump_version.py
        # contain `# C:\Projekte\Hime` as documentation of Path(__file__).parent.parent.
        code_lines = []
        for line in text.splitlines():
            # Simple comment strip: take everything before the first #
            if '#' in line:
                line = line[:line.index('#')]
            code_lines.append(line)
        code_text = "\n".join(code_lines)
        if r"C:\Projekte\Hime" in code_text or "C:/Projekte/Hime" in code_text:
            bad.append(py_file.name)
    if bad:
        _fail("scripts hardcoded paths", ", ".join(bad))
    else:
        _ok("scripts hardcoded paths", "none found")


def check_no_hardcoded_in_tauri_lib() -> None:
    lib = PROJECT_ROOT / "app" / "frontend" / "src-tauri" / "src" / "lib.rs"
    if not lib.exists():
        _warn("lib.rs", "not present")
        return
    text = lib.read_text(encoding="utf-8")
    if r"C:\Projekte\Hime" in text:
        _fail("lib.rs hardcoded path", "still present")
    else:
        _ok("lib.rs hardcoded path", "removed")


def main() -> int:
    print("=== Hime migration verification ===\n")
    check_env_vars()
    check_paths_module()
    check_training_config()
    check_no_hardcoded_paths_in_scripts()
    check_no_hardcoded_in_tauri_lib()
    check_train_with_resume_dry_run()

    fail_count = 0
    for level, label, msg in _results:
        color = {"OK": _GREEN, "WARN": _YELLOW, "FAIL": _RED}[level]
        print(f"  {color}[{level:4}]{_RESET} {label:50} {msg}")
        if level == "FAIL":
            fail_count += 1

    print()
    print(f"Total: {len(_results)} checks, {fail_count} failures")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
