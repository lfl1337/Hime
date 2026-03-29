"""
SmartStoppingCallback — configurable early stopping for HuggingFace Trainer.

Two modes, both configurable:

Mode 1 — Hard Threshold:
  Stop when `target_loss_metric` <= target_loss for N consecutive checks.
  Checked in on_log() (train_loss) or on_evaluate() (eval_loss).

Mode 2 — Patience (Early Stopping):
  Stop when `patience_metric` has not improved by at least `min_delta`
  for `patience` consecutive evaluations.
  Checked in on_evaluate().

Both modes can be active simultaneously — first to trigger wins.
"""
import json
import logging
from pathlib import Path

from transformers import TrainerCallback, TrainerControl, TrainerState, TrainingArguments

logger = logging.getLogger(__name__)


class SmartStoppingCallback(TrainerCallback):

    def __init__(
        self,
        target_loss: float | None = None,
        target_loss_metric: str = "loss",
        target_confirmations: int = 3,
        patience: int | None = None,
        patience_metric: str = "eval_loss",
        min_delta: float = 0.001,
        min_steps: int = 0,
        state_file: str | None = None,
    ):
        self.target_loss = target_loss
        self.target_loss_metric = target_loss_metric
        self.target_confirmations = target_confirmations
        self.patience = patience
        self.patience_metric = patience_metric
        self.min_delta = min_delta
        self.min_steps = min_steps
        self._state_file = Path(state_file) if state_file else None

        # Internal state
        self._target_hit_count = 0
        self._best_metric: float | None = None
        self._patience_counter = 0
        self._stop_reason: str | None = None

    def _write_state(self) -> None:
        if self._state_file is None:
            return
        try:
            state = {
                "patience_counter": self._patience_counter,
                "patience_total": self.patience,
                "target_hit_count": self._target_hit_count,
                "target_confirmations": self.target_confirmations,
                "best_metric": self._best_metric,
                "stop_reason": self._stop_reason,
            }
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(state))
        except Exception:
            pass  # never crash training over a status file

    def on_log(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        logs=None,
        **kwargs,
    ):
        if logs is None or state.global_step < self.min_steps:
            return
        if self.target_loss is None or self.target_loss_metric != "loss":
            return

        current = logs.get("loss")
        if current is None:
            return

        if current <= self.target_loss:
            self._target_hit_count += 1
            logger.info(
                "[SMART STOP] Train loss %.4f <= target %.4f (%d/%d)",
                current, self.target_loss, self._target_hit_count, self.target_confirmations,
            )
            if self._target_hit_count >= self.target_confirmations:
                self._stop_reason = (
                    f"train_loss {current:.4f} <= target {self.target_loss} "
                    f"for {self.target_confirmations} consecutive checks"
                )
                control.should_training_stop = True
        else:
            self._target_hit_count = 0

        self._write_state()

    def on_evaluate(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        metrics=None,
        **kwargs,
    ):
        if metrics is None or state.global_step < self.min_steps:
            return

        # --- Hard threshold on eval_loss ---
        if self.target_loss is not None and self.target_loss_metric == "eval_loss":
            current = metrics.get("eval_loss")
            if current is not None and current <= self.target_loss:
                self._target_hit_count += 1
                logger.info(
                    "[SMART STOP] Eval loss %.4f <= target %.4f (%d/%d)",
                    current, self.target_loss, self._target_hit_count, self.target_confirmations,
                )
                if self._target_hit_count >= self.target_confirmations:
                    self._stop_reason = (
                        f"eval_loss {current:.4f} <= target {self.target_loss} "
                        f"for {self.target_confirmations} consecutive checks"
                    )
                    control.should_training_stop = True
                    self._write_state()
                    return
            elif current is not None:
                self._target_hit_count = 0

        # --- Patience mode ---
        if self.patience is None:
            self._write_state()
            return

        current = metrics.get(self.patience_metric)
        if current is None:
            self._write_state()
            return

        if self._best_metric is None or current < self._best_metric - self.min_delta:
            self._best_metric = current
            self._patience_counter = 0
            logger.info("[SMART STOP] New best %s: %.4f", self.patience_metric, current)
        else:
            self._patience_counter += 1
            logger.info(
                "[SMART STOP] No improvement in %s: %.4f (best: %.4f, patience: %d/%d)",
                self.patience_metric, current, self._best_metric,
                self._patience_counter, self.patience,
            )
            if self._patience_counter >= self.patience:
                self._stop_reason = (
                    f"{self.patience_metric} did not improve by {self.min_delta} "
                    f"for {self.patience} evaluations. Best: {self._best_metric:.4f}"
                )
                control.should_training_stop = True

        self._write_state()

    def on_train_end(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs,
    ):
        if self._stop_reason:
            logger.info("[SMART STOP] Training stopped early: %s", self._stop_reason)
        else:
            logger.info("[SMART STOP] Training completed all epochs (no early stop triggered)")
        self._write_state()
