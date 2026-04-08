"""
TrainerCallback that escalates training data tiers when eval_loss stagnates.

Behavior:
  - Maintains a sliding window of recent `eval_loss` values.
  - If the most recent `patience` evaluations show no improvement greater than
    `min_delta` AND there is a higher-score-loose tier available, sets
    `should_promote_tier = True` and asks the Trainer to stop cleanly.
  - The auto-resume wrapper (scripts/train_with_resume.py) detects the flag and
    restarts the trainer with the next tier.
  - At the loosest tier, the callback no-ops and lets `SmartStoppingCallback`
    take over.

State is persisted to disk after every `on_evaluate` call so a crash mid-run
does not lose the promotion history.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from transformers import TrainerCallback

from .curriculum import Tier

_log = logging.getLogger(__name__)


class PromotionEvent(BaseModel):
    step: int
    from_tier: str
    to_tier: str
    trigger_eval_loss: float


class CurriculumState(BaseModel):
    current_tier_index: int
    current_tier_name: str
    current_min_score: float
    promotion_history: list[PromotionEvent]
    eval_loss_window: list[float]
    last_updated: datetime
    should_promote_tier: bool = False


class CurriculumCallback(TrainerCallback):
    def __init__(
        self,
        tiers: list[Tier],
        state_path: Path,
        patience: int,
        min_delta: float,
    ) -> None:
        if not tiers:
            raise ValueError("tiers must be non-empty")
        self.tiers = tiers
        self.state_path = Path(state_path)
        self.patience = patience
        self.min_delta = min_delta
        self.state = self._load_or_init_state()

    def _load_or_init_state(self) -> CurriculumState:
        if self.state_path.exists():
            try:
                return CurriculumState.model_validate_json(self.state_path.read_text(encoding="utf-8"))
            except Exception as e:
                _log.warning("Failed to read curriculum_state.json (%s) — re-initializing", e)
        return CurriculumState(
            current_tier_index=0,
            current_tier_name=self.tiers[0].name,
            current_min_score=self.tiers[0].min_score,
            promotion_history=[],
            eval_loss_window=[],
            last_updated=datetime.now(UTC),
        )

    def _persist(self) -> None:
        self.state.last_updated = datetime.now(UTC)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(self.state.model_dump_json(indent=2), encoding="utf-8")

    def _should_promote(self) -> bool:
        if self.state.current_tier_index >= len(self.tiers) - 1:
            return False
        window = self.state.eval_loss_window
        if len(window) < self.patience + 1:
            return False
        baseline = window[-(self.patience + 1)]
        recent = window[-self.patience:]
        return all((baseline - v) < self.min_delta for v in recent)

    # ----- TrainerCallback hooks -----

    def on_evaluate(self, args, state, control, metrics=None, **kwargs):  # type: ignore[override]
        if not metrics or "eval_loss" not in metrics:
            return control
        loss = float(metrics["eval_loss"])
        self.state.eval_loss_window.append(loss)
        # Cap window length to avoid unbounded growth
        if len(self.state.eval_loss_window) > 50:
            self.state.eval_loss_window = self.state.eval_loss_window[-50:]

        if self._should_promote():
            current = self.tiers[self.state.current_tier_index]
            next_tier = self.tiers[self.state.current_tier_index + 1]
            self.state.promotion_history.append(
                PromotionEvent(
                    step=int(getattr(state, "global_step", 0)),
                    from_tier=current.name,
                    to_tier=next_tier.name,
                    trigger_eval_loss=loss,
                )
            )
            self.state.should_promote_tier = True
            control.should_training_stop = True
            _log.info(
                "[curriculum] Promoting tier %s → %s at step %d (eval_loss=%.4f)",
                current.name, next_tier.name, getattr(state, "global_step", 0), loss,
            )

        self._persist()
        return control

    # No-op stubs (avoid the callback bug from the prior incident)
    def on_substep_end(self, args, state, control, **kwargs): return control
    def on_epoch_end(self, args, state, control, **kwargs): return control
    def on_step_begin(self, args, state, control, **kwargs): return control
    def on_step_end(self, args, state, control, **kwargs): return control
    def on_log(self, args, state, control, logs=None, **kwargs): return control
    def on_save(self, args, state, control, **kwargs): return control
    def on_train_begin(self, args, state, control, **kwargs): return control
    def on_train_end(self, args, state, control, **kwargs): return control
    def on_init_end(self, args, state, control, **kwargs): return control
