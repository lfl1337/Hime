"""
Pipeline v2 — Stage 2: Translation Merger

Model: google/translategemma-27b-it
Loader: transformers.AutoModelForCausalLM (NOT Unsloth — chat template must be preserved)

merge(drafts, rag_context, glossary_context) → merged EN string

The model is loaded on first call and explicitly unloaded after each call
so Stage 3 can load without competing for VRAM.
"""
from __future__ import annotations

import gc
import logging
import threading
from typing import Any

from .prompts import merger_messages
from ..config.pipeline_v2 import STAGE2_MODEL_ID as _HF_MODEL_ID
from ..config.pipeline_v2 import STAGE2_LOCAL_PATH as _LOCAL_MODEL_DIR

_log = logging.getLogger(__name__)

_MAX_NEW_TOKENS = 1024
_TEMPERATURE = 0.3

# Module-level slots — exposed so tests can assert cleanup
_model: Any | None = None
_tokenizer: Any | None = None
_LOAD_LOCK = threading.Lock()


def _load_model() -> tuple[Any, Any]:
    """Load TranslateGemma-27B from local cache or HuggingFace.

    Uses AutoModelForCausalLM (NOT Unsloth) to preserve the TranslateGemma
    translation chat template, which Unsloth would overwrite.

    Returns:
        (model, tokenizer) tuple ready for inference.
    """
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "transformers and torch are required for Stage 2. "
            "Run: uv add transformers torch"
        ) from exc

    local_path = _LOCAL_MODEL_DIR if _LOCAL_MODEL_DIR.exists() else _HF_MODEL_ID
    _log.info("Stage 2: loading TranslateGemma-27B from %s", local_path)

    tokenizer = AutoTokenizer.from_pretrained(str(local_path), fix_mistral_regex=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(local_path),
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    model.eval()
    _log.info("Stage 2: model loaded")
    return model, tokenizer


async def merge(
    drafts: dict[str, str],
    rag_context: str,
    glossary_context: str,
) -> str:
    """Merge five Stage 1 drafts into one superior translation.

    Loads TranslateGemma-27B, runs a single forward pass, then immediately
    unloads the model so Stage 3 can claim VRAM.

    Args:
        drafts: Dict mapping draft-key → translated text.  Missing keys are
                handled gracefully by merger_messages (shown as [unavailable]).
        rag_context: Retrieved passage context from the RAG store.
        glossary_context: Book-specific glossary formatted for injection.

    Returns:
        The merged English translation string (stripped of leading/trailing
        whitespace and of the input prompt echo).
    """
    global _model, _tokenizer

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("torch is required for Stage 2.") from exc

    with _LOAD_LOCK:
        _model, _tokenizer = _load_model()

    try:
        messages = merger_messages(drafts, rag_context, glossary_context)

        prompt_text: str = _tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        raw_inputs = _tokenizer(prompt_text, return_tensors="pt")
        inputs = raw_inputs.to(_model.device) if hasattr(raw_inputs, "to") else raw_inputs
        # Support both dict-like (BatchEncoding) and attribute-style (tests) access
        input_ids = inputs["input_ids"] if hasattr(inputs, "__getitem__") else inputs.input_ids
        n_input_tokens = len(input_ids[0])

        with torch.inference_mode():
            if hasattr(inputs, "keys"):
                # Real BatchEncoding: unpack all tensors (input_ids + attention_mask)
                output_ids = _model.generate(
                    **inputs,
                    max_new_tokens=_MAX_NEW_TOKENS,
                    do_sample=True,
                    temperature=_TEMPERATURE,
                    pad_token_id=_tokenizer.eos_token_id,
                )
            else:
                output_ids = _model.generate(
                    input_ids,
                    max_new_tokens=_MAX_NEW_TOKENS,
                    do_sample=True,
                    temperature=_TEMPERATURE,
                    pad_token_id=_tokenizer.eos_token_id,
                )

        # Slice off the input tokens so we decode only the new output
        new_tokens = output_ids[0][n_input_tokens:]
        result = _tokenizer.decode(new_tokens, skip_special_tokens=True)
        return result.strip()

    finally:
        # Always unload — even if inference raises
        _log.info("Stage 2: unloading model to free VRAM")
        _model.cpu()
        del _model
        del _tokenizer
        _model = None
        _tokenizer = None
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
