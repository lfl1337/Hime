"""Tests for CurriculumCallback promotion logic and state persistence."""
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.training.curriculum import Tier
from app.training.curriculum_callback import CurriculumCallback, CurriculumState


def make_args():
    return SimpleNamespace(output_dir=".")


def make_state():
    return SimpleNamespace(global_step=1000)


def make_control():
    return SimpleNamespace(should_training_stop=False)


@pytest.fixture
def tiers() -> list[Tier]:
    return [
        Tier("strict",   0.70),
        Tier("expanded", 0.62),
        Tier("loose",    0.55),
    ]


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "curriculum_state.json"


class TestStateInit:
    def test_initializes_at_tier_zero_when_file_missing(self, tiers, state_file):
        cb = CurriculumCallback(
            tiers=tiers, state_path=state_file,
            patience=3, min_delta=0.001,
        )
        assert cb.state.current_tier_index == 0
        assert cb.state.current_tier_name == "strict"
        assert cb.state.current_min_score == 0.70

    def test_loads_existing_state_file(self, tiers, state_file):
        existing = CurriculumState(
            current_tier_index=1,
            current_tier_name="expanded",
            current_min_score=0.62,
            promotion_history=[],
            eval_loss_window=[1.0, 0.99, 0.99],
            last_updated=datetime.now(UTC),
        )
        state_file.write_text(existing.model_dump_json())
        cb = CurriculumCallback(
            tiers=tiers, state_path=state_file,
            patience=3, min_delta=0.001,
        )
        assert cb.state.current_tier_index == 1
        assert cb.state.current_tier_name == "expanded"


class TestPromotionTrigger:
    def test_no_promotion_while_loss_improving(self, tiers, state_file):
        cb = CurriculumCallback(tiers=tiers, state_path=state_file, patience=3, min_delta=0.001)
        control = make_control()
        for loss in [1.10, 1.05, 1.00, 0.95]:
            cb.on_evaluate(make_args(), make_state(), control, metrics={"eval_loss": loss})
        assert cb.state.should_promote_tier is False
        assert control.should_training_stop is False

    def test_promotes_after_patience_stagnant_evals(self, tiers, state_file):
        cb = CurriculumCallback(tiers=tiers, state_path=state_file, patience=3, min_delta=0.001)
        control = make_control()
        # First eval establishes baseline
        cb.on_evaluate(make_args(), make_state(), control, metrics={"eval_loss": 0.95})
        # Three more evals without improvement (delta < min_delta)
        cb.on_evaluate(make_args(), make_state(), control, metrics={"eval_loss": 0.9505})
        cb.on_evaluate(make_args(), make_state(), control, metrics={"eval_loss": 0.9504})
        cb.on_evaluate(make_args(), make_state(), control, metrics={"eval_loss": 0.9499})
        assert cb.state.should_promote_tier is True
        assert control.should_training_stop is True
        assert cb.state.current_tier_index == 0  # not yet incremented; wrapper does that on next start

    def test_no_promotion_at_max_tier(self, tiers, state_file):
        # Pre-load state at the loose tier
        existing = CurriculumState(
            current_tier_index=2,
            current_tier_name="loose",
            current_min_score=0.55,
            promotion_history=[],
            eval_loss_window=[],
            last_updated=datetime.now(UTC),
        )
        state_file.write_text(existing.model_dump_json())
        cb = CurriculumCallback(tiers=tiers, state_path=state_file, patience=3, min_delta=0.001)
        control = make_control()
        # Stagnate
        for loss in [0.80, 0.8005, 0.8001, 0.8002]:
            cb.on_evaluate(make_args(), make_state(), control, metrics={"eval_loss": loss})
        assert cb.state.should_promote_tier is False
        assert control.should_training_stop is False  # SmartStop will handle this


class TestStatePersistence:
    def test_state_written_after_evaluate(self, tiers, state_file):
        cb = CurriculumCallback(tiers=tiers, state_path=state_file, patience=3, min_delta=0.001)
        cb.on_evaluate(make_args(), make_state(), make_control(), metrics={"eval_loss": 0.99})
        assert state_file.exists()
        on_disk = CurriculumState.model_validate_json(state_file.read_text())
        assert on_disk.eval_loss_window[-1] == pytest.approx(0.99)

    def test_no_op_stubs_present(self, tiers, state_file):
        cb = CurriculumCallback(tiers=tiers, state_path=state_file, patience=3, min_delta=0.001)
        # All these should exist and accept (args, state, control, **kwargs) without raising
        cb.on_substep_end(make_args(), make_state(), make_control())
        cb.on_epoch_end(make_args(), make_state(), make_control())
        cb.on_step_begin(make_args(), make_state(), make_control())
        cb.on_step_end(make_args(), make_state(), make_control())
        cb.on_log(make_args(), make_state(), make_control(), logs={})
        cb.on_save(make_args(), make_state(), make_control())
        cb.on_train_begin(make_args(), make_state(), make_control())
        cb.on_train_end(make_args(), make_state(), make_control())
        cb.on_init_end(make_args(), make_state(), make_control())
