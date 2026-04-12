"""
Stage 1D — LLM-jp-3-7.2B-Instruct3 via transformers + BitsAndBytesConfig NF4 4-bit.

Architecture: LlamaForCausalLM (Apache 2.0, sbintuitions via llm-jp project).
Quantization: NF4 4-bit via BitsAndBytesConfig — ~3.7-4.0 GB VRAM footprint.

IMPORTANT: LLM-jp ignores custom system-role content (the chat template hardcodes
a Japanese instruction preamble). The translation instruction and source text MUST
both go in the user role. See stage1_messages_for_model("llm_jp", ...) in prompts.py.

Model path resolution (in priority order):
  1. STAGE1D_LOCAL_PATH from config/pipeline_v2.py (env-var override)
  2. MODELS_DIR / "llm-jp-3-7b" (default)
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

from ...config.pipeline_v2 import STAGE1D_LOCAL_PATH
from ...pipeline.prompts import _LLMJP_STAGE1, render_prompt

_log = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}
_LOAD_LOCK = threading.Lock()


def _model_path() -> str:
    """Return local model directory, falling back to HF repo ID if not present."""
    local = Path(STAGE1D_LOCAL_PATH)
    if local.exists():
        return str(local)
    return "llm-jp/llm-jp-3-7.2b-instruct3"


def _load_model():
    """Load LLM-jp-3-7.2B with NF4 4-bit quantization (idempotent, thread-safe)."""
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]
    with _LOAD_LOCK:
        if "model" in _MODEL_CACHE:
            return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError as exc:
            raise RuntimeError(
                "transformers and bitsandbytes are required for Stage 1D. "
                "Run: uv add transformers bitsandbytes accelerate"
            ) from exc

        path = _model_path()
        _log.info("Loading LLM-jp-3-7.2B from %s (NF4 4-bit)", path)

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        tokenizer = AutoTokenizer.from_pretrained(path)
        model = AutoModelForCausalLM.from_pretrained(
            path,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
        )
        model.eval()
        _MODEL_CACHE["model"] = model
        _MODEL_CACHE["tokenizer"] = tokenizer
        _log.info("LLM-jp-3-7.2B loaded.")
        return model, tokenizer


def _run_inference(source_jp: str, rag_context: str, glossary_context: str) -> str:
    """Blocking inference. Must run in executor — not safe to call from async context."""
    model, tokenizer = _load_model()

    # LLM-jp chat template ignores the system role — put instruction + source in user.
    instruction = render_prompt(
        _LLMJP_STAGE1,
        glossary=glossary_context,
        rag_context=rag_context,
    )
    # Template ends with "Japanese source:" — append source text on next line.
    user_content = instruction + "\n" + source_jp

    messages = [{"role": "user", "content": user_content}]
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
    new_tokens = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


async def translate(
    source_jp: str,
    *,
    rag_context: str = "",
    glossary_context: str = "",
) -> str:
    """
    Translate source_jp with LLM-jp-3-7.2B-Instruct3 (NF4 4-bit).

    Runs blocking model inference in a thread executor so FastAPI's async
    event loop is not blocked. Raises on model load failure or CUDA OOM —
    caller uses return_exceptions=True.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _run_inference, source_jp, rag_context, glossary_context
    )
