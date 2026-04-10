"""
Stage 1C — Qwen3.5-9B via Unsloth, Non-Thinking mode.

Non-Thinking mode is engaged by passing enable_thinking=False to generate().
This suppresses the <think>...</think> reasoning trace and returns a clean
translation directly. Without this flag, output would include long reasoning
blocks that would contaminate the consensus merger.

VRAM footprint: ~6GB at 4-bit quantization.

Model path resolution (in priority order):
  1. settings.hime_qwen35_9b_path  (if non-empty)
  2. MODELS_DIR / "qwen3.5-9b"     (default)

NOTE: unsloth requires separate installation:
  pip install "unsloth[cu124-torch260]" --find-links https://download.pytorch.org/whl/torch_stable.html
  (exact extra depends on CUDA version — see https://github.com/unslothai/unsloth)
"""
from __future__ import annotations

import asyncio
import logging
import threading

from ...config import settings
from ...core.paths import MODELS_DIR
from ...pipeline.prompts import stage1_messages

_log = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}
_LOAD_LOCK = threading.Lock()


def _model_path() -> str:
    if settings.hime_qwen35_9b_path:
        return settings.hime_qwen35_9b_path
    return str(MODELS_DIR / "qwen3.5-9b")


def _load_model():
    """Load Qwen3.5-9B into _MODEL_CACHE (idempotent, thread-safe)."""
    try:
        from unsloth import FastLanguageModel
    except ImportError as exc:
        raise RuntimeError(
            "unsloth is not installed. Install it separately with CUDA support."
        ) from exc
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]
    with _LOAD_LOCK:
        if "model" in _MODEL_CACHE:  # double-check after acquiring lock
            return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]

        path = _model_path()
        _log.info("Loading Qwen3.5-9B from %s", path)
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=path,
            max_seq_length=4096,
            load_in_4bit=True,
        )
        FastLanguageModel.for_inference(model)
        _MODEL_CACHE["model"] = model
        _MODEL_CACHE["tokenizer"] = tokenizer
        _log.info("Qwen3.5-9B loaded.")
        return model, tokenizer


def _run_inference(source_jp: str, rag_context: str, glossary_context: str) -> str:
    model, tokenizer = _load_model()

    messages = stage1_messages(source_jp, rag_context=rag_context, glossary=glossary_context)
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    output_ids = model.generate(
        **inputs,
        max_new_tokens=1024,
        temperature=0.3,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
        enable_thinking=False,  # suppress <think>...</think> blocks
    )
    new_tokens = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


async def translate(
    source_jp: str,
    *,
    rag_context: str = "",
    glossary_context: str = "",
) -> str:
    """
    Translate source_jp with Qwen3.5-9B (Non-Thinking mode).

    Raises on CUDA OOM or model load failure — caller uses return_exceptions=True.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _run_inference, source_jp, rag_context, glossary_context
    )
