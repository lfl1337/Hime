"""Unsloth trainer backend — delegates to train_hime.main() with config overrides."""
from __future__ import annotations

from ..configs import TrainingConfig
from . import register


class UnslothTrainer:
    def validate_config(self, config: TrainingConfig) -> None:
        """Validate model path / tokenizer without loading weights."""
        import os
        from pathlib import Path

        # Check the lora directory will be resolvable
        # (We don't require the model to be present — Phase 2 already downloaded it)
        print(f"[validate:unsloth] key={config.key} model={config.model}")
        print(f"[validate:unsloth] lora_dir={config.lora_dir} max_seq={config.max_seq}")
        print(f"[validate:unsloth] grad_accum={config.grad_accum} moe={config.moe}")

        # Try loading tokenizer (offline, no weights)
        try:
            from transformers import AutoTokenizer
            # Local path preferred; fall back to HF id
            _MODELS_DIR = Path(
                os.environ.get("HIME_MODELS_DIR")
                or str(Path(__file__).resolve().parents[3] / "modelle")
            )
            model_path = _MODELS_DIR / config.lora_dir
            source = str(model_path) if model_path.exists() else config.model
            tok = AutoTokenizer.from_pretrained(source, trust_remote_code=True)
            print(f"[validate:unsloth] tokenizer vocab_size={tok.vocab_size}")
        except Exception as exc:
            print(f"[validate:unsloth] tokenizer probe skipped: {exc}")

    def run(self, config: TrainingConfig, args) -> None:
        """Delegate to train_hime.main() with config values patched in."""
        import importlib
        import os
        import sys
        from pathlib import Path

        # Resolve paths (args override env, env overrides default)
        models_dir = Path(
            getattr(args, 'model_dir', None)
            or os.environ.get("HIME_MODELS_DIR")
            or str(Path(__file__).resolve().parents[3] / "modelle")
        )
        training_dir = Path(
            getattr(args, 'training_data', None)
            or os.environ.get("HIME_TRAINING_DATA_DIR")
            or str(Path(__file__).resolve().parents[3] / "data" / "training")
        )
        output_dir = models_dir / "lora" / config.lora_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Ensure scripts/ is importable
        scripts_dir = str(Path(__file__).resolve().parents[3])
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        # Import train_hime (triggers unsloth init on first import)
        _th = importlib.import_module("train_hime")

        # Patch module-level globals so all functions pick up config values
        lora_rank = getattr(args, 'rank', None) or 16
        _th.MODEL_NAME     = config.model
        _th.MAX_SEQ_LEN    = config.max_seq
        _th.BATCH_SIZE     = config.batch_size
        _th.GRAD_ACCUM     = config.grad_accum
        _th.LORA_RANK      = lora_rank
        _th.LORA_ALPHA     = lora_rank * 2
        _th.LORA_DROPOUT   = config.lora_dropout   # 0.0 → Unsloth fast path enabled
        _th.OUTPUT_DIR     = output_dir
        _th.TRAINING_DIR   = training_dir
        _th.ADAPTER_NAME   = config.lora_dir

        # Build stop config from CLI args
        tl = getattr(args, 'target_loss', None)
        pa = getattr(args, 'patience', None)
        if tl is not None and pa is not None:
            mode = 'both'
        elif tl is not None:
            mode = 'threshold'
        elif pa is not None:
            mode = 'patience'
        else:
            mode = 'none'

        stop_config = {
            'stop_mode':             mode,
            'target_loss':           tl,
            'target_loss_metric':    'loss',
            'target_confirmations':  3,
            'patience':              pa,
            'patience_metric':       'eval_loss',
            'min_delta':             getattr(args, 'min_delta', None) or 0.001,
            'min_steps':             getattr(args, 'min_steps', None) or 0,
            'max_epochs':            getattr(args, 'max_epochs', None) or 3,
            'max_steps':             getattr(args, 'max_steps', None),
        }

        full_resume = getattr(args, 'full_resume', False)
        fresh       = getattr(args, 'fresh', False)
        resume_cp   = getattr(args, 'resume', None)

        _th.main(
            resume_from_checkpoint=resume_cp,
            stop_config=stop_config,
            warm_start=not full_resume and not fresh,
            full_resume=full_resume,
        )


register("unsloth", UnslothTrainer())
