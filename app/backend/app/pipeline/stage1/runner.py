"""
Stage 1 v2 orchestrator — runs all 5 adapters and returns Stage1Drafts.

Execution strategy:
  - 1A (Qwen32B/Ollama) always runs in parallel with local models.
    It has no VRAM footprint in our process (Ollama manages its own memory).
  - 1B, 1C, 1D (local Unsloth) are attempted in parallel first.
    If any result is a CUDA OOM error, ALL local adapters are retried
    sequentially with VRAM cleanup between each call.
  - 1E (JMdict) is CPU-only, called synchronously before gather; its result
    is always available.

OOM detection heuristic: RuntimeError with "CUDA out of memory" in the message,
or torch.cuda.OutOfMemoryError (available in PyTorch >= 2.0).
"""
from __future__ import annotations

import asyncio
import gc
import logging
from typing import Any

from ._types import Stage1Drafts
from . import (
    adapter_qwen32b,
    adapter_translategemma,
    adapter_qwen35_9b,
    adapter_gemma4,
    adapter_jmdict,
)

_log = logging.getLogger(__name__)


def _is_oom(exc: BaseException) -> bool:
    """Return True if exc is a CUDA out-of-memory error."""
    msg = str(exc).lower()
    if "cuda out of memory" in msg:
        return True
    # PyTorch >= 2.0 raises a dedicated type
    try:
        import torch
        if isinstance(exc, torch.cuda.OutOfMemoryError):
            return True
    except (ImportError, AttributeError):
        pass
    return False


def _vram_cleanup() -> None:
    """Free cached GPU memory between sequential adapter calls."""
    try:
        import torch
        torch.cuda.empty_cache()
    except (ImportError, AttributeError):
        pass
    gc.collect()


async def _run_local_adapters_parallel(
    source_jp: str,
    rag_context: str,
    glossary_context: str,
) -> tuple[Any, Any, Any]:
    """
    Run adapters 1B, 1C, 1D in parallel.
    Returns a 3-tuple of (result_or_exception, ...) — never raises.
    """
    results = await asyncio.gather(
        adapter_translategemma.translate(source_jp, rag_context=rag_context, glossary_context=glossary_context),
        adapter_qwen35_9b.translate(source_jp, rag_context=rag_context, glossary_context=glossary_context),
        adapter_gemma4.translate(source_jp, rag_context=rag_context, glossary_context=glossary_context),
        return_exceptions=True,
    )
    return results[0], results[1], results[2]


async def _run_local_adapters_sequential(
    source_jp: str,
    rag_context: str,
    glossary_context: str,
) -> tuple[Any, Any, Any]:
    """
    Run adapters 1B, 1C, 1D one at a time with VRAM cleanup between each.
    Returns a 3-tuple of (result_or_exception, ...) — never raises.
    """
    _log.warning(
        "VRAM OOM detected in parallel run — falling back to sequential local inference."
    )

    results: list[Any] = []
    adapters = [
        adapter_translategemma.translate,
        adapter_qwen35_9b.translate,
        adapter_gemma4.translate,
    ]
    adapter_names = ["translategemma", "qwen35_9b", "gemma4"]

    for fn, name in zip(adapters, adapter_names):
        try:
            _vram_cleanup()
            out = await fn(source_jp, rag_context=rag_context, glossary_context=glossary_context)
            results.append(out)
        except Exception as exc:  # noqa: BLE001
            _log.warning("Sequential adapter %s failed: %s", name, exc)
            results.append(exc)

    return results[0], results[1], results[2]


def _extract(result: Any, name: str) -> str | None:
    """Convert a gather result (value or exception) to str or None."""
    if isinstance(result, BaseException):
        _log.warning("Stage 1 adapter '%s' failed: %s", name, result)
        return None
    if isinstance(result, str) and result.strip():
        return result
    if isinstance(result, str) and not result.strip():
        _log.warning("Stage 1 adapter '%s' returned empty string", name)
        return None
    return None


async def run_stage1(
    segment: str,
    rag_context: str,
    glossary_context: str,
    notes: str = "",
) -> Stage1Drafts:
    """
    Run all Stage 1 adapters and return a Stage1Drafts dataclass.

    Never raises. Adapter failures → None fields (except jmdict, always a str).
    """
    # 1E — always run first (fast, CPU-only)
    jmdict_result = adapter_jmdict.translate(segment)

    # 1A + 1B/1C/1D in parallel (Ollama is independent of local VRAM)
    qwen32b_coro = adapter_qwen32b.translate(
        segment, rag_context=rag_context, glossary_context=glossary_context, notes=notes
    )
    local_coro = _run_local_adapters_parallel(segment, rag_context, glossary_context)

    gather_results = await asyncio.gather(qwen32b_coro, local_coro, return_exceptions=True)

    qwen32b_raw = gather_results[0]
    local_raw = gather_results[1]

    # Unwrap 1A
    if isinstance(qwen32b_raw, BaseException):
        _log.warning("Adapter 1A (qwen32b) failed: %s", qwen32b_raw)
        qwen32b_result: str | None = None
    else:
        qwen32b_result = qwen32b_raw if isinstance(qwen32b_raw, str) and qwen32b_raw.strip() else None

    # Unwrap 1B/1C/1D — detect OOM and retry sequentially if needed
    if isinstance(local_raw, BaseException):
        # The whole _run_local_adapters_parallel coroutine raised — treat as OOM
        _log.warning("Local adapter gather raised: %s — retrying sequentially", local_raw)
        tgemma_raw, q35_raw, g4_raw = await _run_local_adapters_sequential(
            segment, rag_context, glossary_context
        )
    else:
        tgemma_raw, q35_raw, g4_raw = local_raw
        # Check if any of the parallel results was an OOM
        if any(_is_oom(r) for r in (tgemma_raw, q35_raw, g4_raw) if isinstance(r, BaseException)):
            tgemma_raw, q35_raw, g4_raw = await _run_local_adapters_sequential(
                segment, rag_context, glossary_context
            )

    return Stage1Drafts(
        source_jp=segment,
        jmdict=jmdict_result,
        qwen32b=qwen32b_result,
        translategemma12b=_extract(tgemma_raw, "translategemma"),
        qwen35_9b=_extract(q35_raw, "qwen35_9b"),
        gemma4_e4b=_extract(g4_raw, "gemma4"),
    )
