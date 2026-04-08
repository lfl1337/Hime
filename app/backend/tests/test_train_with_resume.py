"""Tests for the train_with_resume wrapper script."""
import sys
from pathlib import Path

import pytest

# scripts/ is not a package; insert it into sys.path so we can import the module
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import train_with_resume as twr  # noqa: E402


class TestFindNewestValidCheckpoint:
    def test_returns_none_for_empty_dir(self, tmp_path: Path):
        assert twr.find_newest_valid_checkpoint(tmp_path) is None

    def test_returns_none_when_only_invalid_checkpoints(self, tmp_path: Path):
        cp = tmp_path / "checkpoint-100"
        cp.mkdir()
        (cp / "trainer_state.json").write_text("{}")
        # Missing optimizer.pt and scheduler.pt
        assert twr.find_newest_valid_checkpoint(tmp_path) is None

    def test_returns_only_complete_checkpoint(self, tmp_path: Path):
        cp = tmp_path / "checkpoint-200"
        cp.mkdir()
        (cp / "trainer_state.json").write_text("{}")
        (cp / "optimizer.pt").write_bytes(b"")
        (cp / "scheduler.pt").write_bytes(b"")
        assert twr.find_newest_valid_checkpoint(tmp_path) == cp

    def test_picks_newest_by_step_number(self, tmp_path: Path):
        for step in (100, 500, 250):
            cp = tmp_path / f"checkpoint-{step}"
            cp.mkdir()
            (cp / "trainer_state.json").write_text("{}")
            (cp / "optimizer.pt").write_bytes(b"")
            (cp / "scheduler.pt").write_bytes(b"")
        result = twr.find_newest_valid_checkpoint(tmp_path)
        assert result == tmp_path / "checkpoint-500"

    def test_skips_checkpoints_missing_optimizer(self, tmp_path: Path):
        # checkpoint-300 has everything; checkpoint-400 is missing optimizer
        good = tmp_path / "checkpoint-300"
        good.mkdir()
        (good / "trainer_state.json").write_text("{}")
        (good / "optimizer.pt").write_bytes(b"")
        (good / "scheduler.pt").write_bytes(b"")
        bad = tmp_path / "checkpoint-400"
        bad.mkdir()
        (bad / "trainer_state.json").write_text("{}")
        (bad / "scheduler.pt").write_bytes(b"")
        # The newer one is invalid → falls back to the older one
        assert twr.find_newest_valid_checkpoint(tmp_path) == good

    def test_ignores_non_checkpoint_dirs(self, tmp_path: Path):
        (tmp_path / "garbage_folder").mkdir()
        (tmp_path / "config.json").write_text("{}")
        cp = tmp_path / "checkpoint-50"
        cp.mkdir()
        (cp / "trainer_state.json").write_text("{}")
        (cp / "optimizer.pt").write_bytes(b"")
        (cp / "scheduler.pt").write_bytes(b"")
        assert twr.find_newest_valid_checkpoint(tmp_path) == cp
