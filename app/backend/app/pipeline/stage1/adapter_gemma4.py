"""
Stage 1D — Gemma4 E4B GGUF via Unsloth GGUF inference.

Gemma4 is loaded from a .gguf file. Unsloth's FastLanguageModel.from_pretrained
accepts GGUF paths directly — pass the full path to the .gguf file.

Gemma4 does NOT support the enable_thinking parameter — do not pass it.

VRAM footprint: ~4GB at E4B quantization (4-bit).

Model path resolution (in priority order):
  1. settings.hime_gemma4_path      (if non-empty; should point to the .gguf file)
  2. MODELS_DIR / "gemma4-e4b"      (directory — Unsloth auto-finds the .gguf inside)

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


class _UnslothStub:
    """Placeholder used when unsloth is not installed.

    from_pretrained raises a descriptive RuntimeError so callers get a clear
    message rather than a silent mock that produces garbage output.
    for_inference is a no-op to allow test patches to work without unsloth.
    """

    @staticmethod
    def from_pretrained(*args, **kwargs):
        raise RuntimeError(
            "unsloth not installed; run: pip install 'unsloth[cu124-torch260]'"
        )

    @staticmethod
    def for_inference(model):
        pass


try:
    from unsloth import FastLanguageModel  # noqa: PLC0415
except ImportError:
    FastLanguageModel = _UnslothStub()  # type: ignore[assignment]


def _model_path() -> str:
    if settings.hime_gemma4_path:
        return settings.hime_gemma4_path
    return str(MODELS_DIR / "gemma4-e4b")


def _load_model():
    """Load Gemma4 E4B GGUF into _MODEL_CACHE (idempotent, thread-safe)."""
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]
    with _LOAD_LOCK:
        if "model" in _MODEL_CACHE:  # double-check after acquiring lock
            return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]

        path = _model_path()
        _log.info("Loading Gemma4 E4B GGUF from %s", path)
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=path,
            max_seq_length=4096,
            load_in_4bit=True,
        )
        FastLanguageModel.for_inference(model)
        _MODEL_CACHE["model"] = model
        _MODEL_CACHE["tokenizer"] = tokenizer
        _log.info("Gemma4 E4B loaded.")
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
        # NOTE: enable_thinking is intentionally omitted — Gemma4 does not support it
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
    Translate source_jp with Gemma4 E4B (GGUF, non-thinking not applicable).

    Raises on CUDA OOM or model load failure — caller uses return_exceptions=True.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _run_inference, source_jp, rag_context, glossary_context
    )
