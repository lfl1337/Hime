"""
Stage 1B — TranslateGemma-12B via Unsloth local inference.

Model is loaded lazily on first call and cached for the process lifetime.
TranslateGemma has its own chat template; we use apply_chat_template() as
the model card recommends rather than building messages manually.

VRAM footprint: ~8GB at 4-bit quantization.

Model path resolution (in priority order):
  1. settings.hime_translategemma_path  (if non-empty)
  2. MODELS_DIR / "translategemma-12b"  (default)

NOTE: unsloth requires separate installation:
  pip install "unsloth[cu124-torch260]" --find-links https://download.pytorch.org/whl/torch_stable.html
  (exact extra depends on CUDA version — see https://github.com/unslothai/unsloth)
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

from ...config import settings
from ...core.paths import MODELS_DIR

_log = logging.getLogger(__name__)

# Module-level cache — keys: "model", "tokenizer"
# Using a dict so tests can call .clear() to reset state between test runs.
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
    if settings.hime_translategemma_path:
        return settings.hime_translategemma_path
    return str(MODELS_DIR / "translategemma-12b")


def _load_model():
    """Load TranslateGemma-12B into _MODEL_CACHE (idempotent, thread-safe)."""
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]
    with _LOAD_LOCK:
        if "model" in _MODEL_CACHE:  # double-check after acquiring lock
            return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]

        path = _model_path()
        _log.info("Loading TranslateGemma-12B from %s", path)
        model, tokenizer = FastLanguageModel.from_pretrained(  # type: ignore[union-attr]
            model_name=path,
            max_seq_length=4096,
            load_in_4bit=True,
        )
        FastLanguageModel.for_inference(model)
        _MODEL_CACHE["model"] = model
        _MODEL_CACHE["tokenizer"] = tokenizer
        _log.info("TranslateGemma-12B loaded.")
        return model, tokenizer


def _run_inference(source_jp: str, rag_context: str, glossary_context: str) -> str:
    """Blocking inference call — run in executor to avoid blocking the event loop."""
    model, tokenizer = _load_model()

    # Build the conversation in the format TranslateGemma expects.
    system_content = (
        "You are an expert Japanese-to-English light novel translator. "
        "Translate the text accurately, preserving style, tone, and honorifics."
    )
    if glossary_context:
        system_content += f"\n\nGlossary:\n{glossary_context}"
    if rag_context:
        system_content += f"\n\nContext from previous passages:\n{rag_context}"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": source_jp},
    ]

    # TranslateGemma uses its own template — do NOT build raw prompt manually.
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
    )
    # Decode only newly generated tokens (skip the prompt)
    new_tokens = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


async def translate(
    source_jp: str,
    *,
    rag_context: str = "",
    glossary_context: str = "",
) -> str:
    """
    Translate source_jp with TranslateGemma-12B.

    Runs blocking model inference in a thread executor so FastAPI's async
    event loop is not blocked. Raises on model load failure or CUDA OOM —
    caller uses return_exceptions=True.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _run_inference, source_jp, rag_context, glossary_context
    )
