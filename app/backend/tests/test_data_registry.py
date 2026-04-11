"""Tests for scripts/hime_data.py: register / list / export commands + backend router."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "hime_data.py"


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(cwd), timeout=60,
    )


@pytest.fixture
def tmp_repo(tmp_path):
    """Minimal repo layout for CLI tests."""
    (tmp_path / "data" / "training").mkdir(parents=True)
    sample = tmp_path / "data" / "training" / "sample.jsonl"
    lines = [
        {"input": "こんにちは", "output": "Hello", "score": 0.80},
        {"input": "ありがとう", "output": "Thank you", "score": 0.75},
        {"input": "さようなら", "output": "Goodbye", "score": 0.65},
    ]
    sample.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    return tmp_path


def test_register_new_entry(tmp_repo):
    result = _run_cli(
        "register", "data/training/sample.jsonl",
        "--id", "sample", "--kind", "parallel_corpus",
        "--source", "Test", "--quality-field", "score",
        cwd=tmp_repo,
    )
    assert result.returncode == 0, result.stderr
    registry = tmp_repo / "data" / "registry.jsonl"
    assert registry.exists()
    entries = [json.loads(l) for l in registry.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(entries) == 1
    assert entries[0]["id"] == "sample"
    assert entries[0]["lines"] == 3
    assert entries[0]["quality_range"] == [0.65, 0.80]


def test_list_shows_registered_entries(tmp_repo):
    _run_cli(
        "register", "data/training/sample.jsonl",
        "--id", "sample", "--kind", "parallel_corpus",
        "--source", "Test", "--quality-field", "score",
        cwd=tmp_repo,
    )
    result = _run_cli("list", cwd=tmp_repo)
    assert result.returncode == 0
    assert "sample" in result.stdout
    assert "3" in result.stdout


def test_export_filters_by_min_score(tmp_repo):
    _run_cli(
        "register", "data/training/sample.jsonl",
        "--id", "sample", "--kind", "parallel_corpus",
        "--source", "Test", "--quality-field", "score",
        cwd=tmp_repo,
    )
    out_path = tmp_repo / "filtered.jsonl"
    result = _run_cli(
        "export", "--min-score", "0.70",
        "--out", str(out_path),
        cwd=tmp_repo,
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()
    filtered = [json.loads(l) for l in out_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(filtered) == 2  # 0.80 and 0.75 pass; 0.65 filtered out


def test_register_refuses_duplicate_id(tmp_repo):
    _run_cli(
        "register", "data/training/sample.jsonl",
        "--id", "sample", "--kind", "parallel_corpus",
        "--source", "Test", "--quality-field", "score",
        cwd=tmp_repo,
    )
    result = _run_cli(
        "register", "data/training/sample.jsonl",
        "--id", "sample", "--kind", "parallel_corpus",
        "--source", "Test", "--quality-field", "score",
        cwd=tmp_repo,
    )
    assert result.returncode != 0, "Duplicate id should fail"
    assert "already exists" in result.stderr or "duplicate" in result.stderr.lower()


# --- Backend router tests --------------------------------------------------

def test_router_get_registry_returns_list(tmp_path, monkeypatch):
    """GET /api/v1/data/registry returns the registry as JSON."""
    from fastapi.testclient import TestClient

    # Write a registry file in tmp_path/data/registry.jsonl
    reg_dir = tmp_path / "data"
    reg_dir.mkdir(parents=True, exist_ok=True)
    reg_file = reg_dir / "registry.jsonl"
    reg_file.write_text(json.dumps({
        "id": "test_src", "path": "data/training/test.jsonl",
        "kind": "parallel_corpus", "source": "Test", "lines": 10,
        "quality_field": "score", "quality_range": [0.5, 0.9],
        "added": "2026-04-11T00:00:00Z", "notes": "",
    }) + "\n", encoding="utf-8")

    # Patch the router's DATA_DIR directly before import
    monkeypatch.setenv("HIME_DATA_DIR", str(reg_dir))

    # Reload the router module so it picks up the new DATA_DIR
    import importlib
    import app.routers.data_registry as dr_module
    import app.core.paths as paths_module

    # Patch DATA_DIR on both the paths module and router module
    monkeypatch.setattr(paths_module, "DATA_DIR", reg_dir)
    monkeypatch.setattr(dr_module, "DATA_DIR", reg_dir)

    from app.main import app
    with TestClient(app) as client:
        resp = client.get("/api/v1/data/registry")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(e["id"] == "test_src" for e in data)
