"""ManualSaveCallback — watches for SAVE_NOW signal file to trigger immediate checkpoint."""
from pathlib import Path
from transformers import TrainerCallback, TrainerControl, TrainerState, TrainingArguments


class ManualSaveCallback(TrainerCallback):
    def on_step_end(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs,
    ) -> TrainerControl:
        signal = Path(args.output_dir) / "SAVE_NOW"
        if signal.exists():
            try:
                signal.unlink()
            except OSError:
                pass
            control.should_save = True
            print(f"[MANUAL SAVE] Checkpoint wird gespeichert bei Step {state.global_step}")
        return control
