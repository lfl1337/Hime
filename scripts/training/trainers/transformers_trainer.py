"""Transformers trainer backend (for TranslateGemma-12B) — validate_config only."""
from __future__ import annotations

from ..configs import TrainingConfig
from . import register


class TransformersTrainer:
    def validate_config(self, config: TrainingConfig) -> None:
        """Validate model path / tokenizer without loading weights."""
        import os
        from pathlib import Path

        print(f"[validate:transformers] key={config.key} model={config.model}")
        print(f"[validate:transformers] lora_dir={config.lora_dir} max_seq={config.max_seq}")
        print(f"[validate:transformers] note: {config.notes}")

        tok = None
        try:
            from transformers import AutoTokenizer
            _MODELS_DIR = Path(
                os.environ.get("HIME_MODELS_DIR")
                or str(Path(__file__).resolve().parents[3] / "modelle")
            )
            model_path = _MODELS_DIR / config.lora_dir
            source = str(model_path) if model_path.exists() else config.model
            tok = AutoTokenizer.from_pretrained(
                source, trust_remote_code=True, fix_mistral_regex=True
            )
            print(f"[validate:transformers] tokenizer vocab_size={tok.vocab_size}")
        except (ImportError, OSError) as exc:
            print(f"[validate:transformers] tokenizer probe skipped: {exc}")

        # Verify chat template is present (critical for TranslateGemma)
        # This check runs only if tokenizer loaded successfully; AssertionError is NOT caught
        if tok is not None:
            assert hasattr(tok, "chat_template") and tok.chat_template, (
                "TranslateGemma tokenizer must have a chat_template — this is required "
                "to preserve the translation format during fine-tuning."
            )
            print("[validate:transformers] chat_template=OK")

    def run(self, config: TrainingConfig, args) -> None:
        raise NotImplementedError(
            "TransformersTrainer.run() not executed in this session. Use --validate-config."
        )


register("transformers", TransformersTrainer())
