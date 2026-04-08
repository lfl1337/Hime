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


class TestRetryLoop:
    def test_zero_exit_returns_immediately(self, monkeypatch, tmp_path: Path):
        calls = []
        def fake_runner(cmd, log_path):
            calls.append(cmd)
            return 0
        monkeypatch.setattr(twr, "run_training_subprocess", fake_runner)
        rc = twr.run_with_retries(
            cmd=["python", "fake.py"],
            log_path=tmp_path / "auto_resume.log",
            max_restarts=5,
            checkpoint_dir=tmp_path / "checkpoints",
            model_name="X",
            model_key=None,
            epochs=1.0,
            curriculum_state_path=None,
        )
        assert rc == 0
        assert len(calls) == 1

    def test_retries_on_nonzero_exit(self, monkeypatch, tmp_path: Path):
        attempts = {"n": 0}
        def fake_runner(cmd, log_path):
            attempts["n"] += 1
            return 1 if attempts["n"] < 3 else 0
        monkeypatch.setattr(twr, "run_training_subprocess", fake_runner)
        monkeypatch.setattr(twr.time, "sleep", lambda _s: None)
        rc = twr.run_with_retries(
            cmd=["python", "fake.py"],
            log_path=tmp_path / "auto_resume.log",
            max_restarts=5,
            checkpoint_dir=tmp_path / "checkpoints",
            model_name="X",
            model_key=None,
            epochs=1.0,
            curriculum_state_path=None,
        )
        assert rc == 0
        assert attempts["n"] == 3

    def test_aborts_after_max_restarts(self, monkeypatch, tmp_path: Path):
        attempts = {"n": 0}
        def fake_runner(cmd, log_path):
            attempts["n"] += 1
            return 1  # always fails

        monkeypatch.setattr(twr, "run_training_subprocess", fake_runner)
        monkeypatch.setattr(twr.time, "sleep", lambda _s: None)
        rc = twr.run_with_retries(
            cmd=["python", "fake.py"],
            log_path=tmp_path / "auto_resume.log",
            max_restarts=2,
            checkpoint_dir=tmp_path / "checkpoints",
            model_name="X",
            model_key=None,
            epochs=1.0,
            curriculum_state_path=None,
        )
        assert rc == 1
        assert attempts["n"] == 3  # 1 initial + 2 retries, then abort (locks the strict-> boundary)

    def test_tier_promotion_does_not_count_as_crash(self, monkeypatch, tmp_path: Path):
        cs_path = tmp_path / "curriculum_state.json"
        cs_path.write_text(
            '{"current_tier_index": 0, "current_tier_name": "strict", '
            '"current_min_score": 0.7, "promotion_history": [], "eval_loss_window": [], '
            '"last_updated": "2026-04-08T00:00:00+00:00", "should_promote_tier": true}'
        )
        # Schema guard: if CurriculumState evolves, this fails before the test runs
        from app.training.curriculum_callback import CurriculumState
        CurriculumState.model_validate_json(cs_path.read_text())
        attempts = {"n": 0}
        def fake_runner(cmd, log_path):
            attempts["n"] += 1
            return 0
        monkeypatch.setattr(twr, "run_training_subprocess", fake_runner)
        rc = twr.run_with_retries(
            cmd=["python", "fake.py"],
            log_path=tmp_path / "auto_resume.log",
            max_restarts=2,
            checkpoint_dir=tmp_path / "checkpoints",
            model_name="X",
            model_key=None,
            epochs=1.0,
            curriculum_state_path=cs_path,
        )
        assert rc == 0
        assert attempts["n"] == 1
