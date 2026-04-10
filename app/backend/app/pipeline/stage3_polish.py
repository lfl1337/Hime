"""
Pipeline v2 — Stage 3: Literary Polish

Model: Qwen/Qwen3-30B-A3B via Unsloth NF4 (non-thinking mode)

This module provides:
  convert_jp_punctuation(text) — pure function, no GPU required
  polish(merged, glossary_context) — async, loads/unloads the model
  unload_stage3() — explicit VRAM cleanup
"""
from __future__ import annotations

import gc
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from .prompts import polish_messages

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Punctuation conversion table (order matters: longer patterns first)
# ---------------------------------------------------------------------------
_PUNCT_TABLE: list[tuple[str | re.Pattern, str]] = [
    # Paired brackets — must come before single characters
    ("「",  '"'),
    ("」",  '"'),
    ("『",  "'"),
    ("』",  "'"),
    # Single characters
    ("…",  "..."),
    ("！",  "!"),
    ("？",  "?"),
    ("、",  ","),
    # 。 → strip everywhere (English punctuation from the model handles breaks)
    ("。",  ""),
]


def convert_jp_punctuation(text: str) -> str:
    """Replace Japanese punctuation with English equivalents.

    This is a pure function — no model, no GPU, fully testable in isolation.

    Conversion rules:
        「」 → double quotation marks
        『』 → single quotation marks
        …   → ...
        ！   → !
        ？   → ?
        、   → ,
        。   → removed (English prose uses periods from the model output)

    Args:
        text: Raw text that may contain Japanese punctuation.

    Returns:
        Text with Japanese punctuation replaced.
    """
    if not text:
        return text
    for pattern, replacement in _PUNCT_TABLE:
        if isinstance(pattern, re.Pattern):
            text = pattern.sub(replacement, text)
        else:
            text = text.replace(pattern, replacement)
    return text


# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
_HF_MODEL_ID = "Qwen/Qwen3-30B-A3B"
_MODELS_DIR = Path(
    os.environ.get("HIME_MODELS_DIR")
    or Path(__file__).resolve().parents[4] / "modelle"
)
_LOCAL_MODEL_DIR = _MODELS_DIR / "qwen3-30b"

_MAX_NEW_TOKENS = 1024
_TEMPERATURE = 0.2

# Module-level slots — exposed so tests can assert cleanup
_model: Any | None = None
_tokenizer: Any | None = None
_LOAD_LOCK = threading.Lock()


def _load_model() -> tuple[Any, Any]:
    """Load Qwen3-30B-A3B via Unsloth (NF4 quantisation, non-thinking mode).

    Non-thinking mode: Qwen3 skips the <think>...</think> chain-of-thought
    preamble and emits only the final answer.

    Returns:
        (model, tokenizer) tuple ready for inference.
    """
    try:
        from unsloth import FastLanguageModel
    except ImportError as exc:
        raise RuntimeError(
            "unsloth is required for Stage 3. "
            "Install via: pip install unsloth"
        ) from exc

    local_path = str(_LOCAL_MODEL_DIR) if _LOCAL_MODEL_DIR.exists() else _HF_MODEL_ID
    _log.info("Stage 3: loading Qwen3-30B-A3B (NF4) from %s", local_path)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=local_path,
        max_seq_length=4096,
        load_in_4bit=True,
        dtype=None,  # auto-detect (bfloat16 on Ampere+)
    )
    FastLanguageModel.for_inference(model)
    _log.info("Stage 3: model loaded")
    return model, tokenizer


async def polish(
    merged: str,
    glossary_context: str,
    retry_instruction: str = "",
) -> str:
    """Polish the merged Stage 2 translation for literary quality.

    Steps:
    1. Run convert_jp_punctuation() on the merged text so the model sees
       clean English punctuation.
    2. Build the message list via polish_messages().
    3. Load Qwen3-30B-A3B, run inference in non-thinking mode.
    4. Unload model (cpu() + del + cuda.empty_cache()) unconditionally.

    Args:
        merged: The merged English translation from Stage 2.
        glossary_context: Book-specific glossary for honorific consistency.
        retry_instruction: Optional additional instruction injected on retry
                           (e.g. "Focus on fixing dialogue formatting.").

    Returns:
        Final polished English translation string.
    """
    global _model, _tokenizer

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("torch is required for Stage 3.") from exc

    # Step 1: Pre-convert punctuation before the model processes the text
    pre_converted = convert_jp_punctuation(merged)

    with _LOAD_LOCK:
        _model, _tokenizer = _load_model()

    try:
        messages = polish_messages(
            merged=pre_converted,
            glossary_context=glossary_context,
            retry_instruction=retry_instruction,
        )

        prompt_text: str = _tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = _tokenizer(prompt_text, return_tensors="pt")
        input_ids = inputs.input_ids
        n_input_tokens = len(input_ids[0])

        with torch.inference_mode():
            output_ids = _model.generate(
                input_ids,
                max_new_tokens=_MAX_NEW_TOKENS,
                do_sample=True,
                temperature=_TEMPERATURE,
                pad_token_id=_tokenizer.eos_token_id,
            )

        new_tokens = output_ids[0][n_input_tokens:]
        result = _tokenizer.decode(new_tokens, skip_special_tokens=True)
        return result.strip()

    finally:
        # CRITICAL: must unload before Stage 4 loads
        _log.info("Stage 3: unloading model to free VRAM")
        _model.cpu()
        del _model
        del _tokenizer
        _model = None
        _tokenizer = None
        gc.collect()
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass


def unload_stage3() -> None:
    """Explicitly unload Stage 3 model from VRAM.

    Call this after polish() if you need to reclaim VRAM for Stage 4.
    Note: polish() already unloads automatically after each call.
    This function is a safety net for edge cases.
    """
    global _model, _tokenizer
    if _model is not None:
        try:
            _model.cpu()
        except Exception:
            pass
        del _model
        _model = None
    if _tokenizer is not None:
        del _tokenizer
        _tokenizer = None
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass
    _log.info("Stage 3: explicit unload complete")
