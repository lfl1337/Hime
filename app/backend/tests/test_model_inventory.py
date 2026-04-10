"""Tests for model_inventory_report.py helper functions."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))
import model_inventory_report as inv


def test_format_size():
    assert inv.format_size(0) == "0 B"
    assert inv.format_size(1024) == "1.0 KB"
    assert inv.format_size(1024 ** 3) == "1.0 GB"
    assert inv.format_size(1024 ** 3 * 32) == "32.0 GB"


def test_scan_dir_empty(tmp_path):
    result = inv.scan_dir(tmp_path / "nonexistent")
    assert result == {"exists": False, "total_bytes": 0, "items": []}


def test_scan_dir_with_files(tmp_path):
    (tmp_path / "model.bin").write_bytes(b"x" * 1024)
    (tmp_path / "config.json").write_bytes(b"{}")
    result = inv.scan_dir(tmp_path)
    assert result["exists"] is True
    assert result["total_bytes"] == 1026
    assert len(result["items"]) == 2


def test_report_contains_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(inv, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(inv, "MODELS_DIR", tmp_path / "modelle")
    monkeypatch.setattr(inv, "HF_CACHE", tmp_path / "hf_cache")
    (tmp_path / "modelle").mkdir(parents=True)
    (tmp_path / "hf_cache").mkdir(parents=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="NAME\ngemma:latest 3.2 GB\n")
        report = inv.build_report()

    assert "## Ollama Modelle" in report
    assert "## HuggingFace Cache" in report
    assert "## Qwen2.5-32B Checkpoints" in report
    assert "## Gesamtverbrauch" in report
