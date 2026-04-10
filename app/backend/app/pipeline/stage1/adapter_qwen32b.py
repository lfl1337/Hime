"""
Stage 1A — Qwen2.5-32B LoRA via Ollama (existing infrastructure).

Reuses app.inference.complete() against the hime_qwen32b endpoint already
configured in settings. This is identical to what pipeline/runner.py did for
"qwen32b" in the old 3-model gather, but extracted as a standalone function
so the stage1 package can call it independently.
"""
from __future__ import annotations

from ...config import settings
from ...inference import complete
from ...pipeline.prompts import stage1_messages


async def translate(
    source_jp: str,
    *,
    rag_context: str = "",
    glossary_context: str = "",
    notes: str = "",
) -> str:
    """
    Call the Qwen2.5-32B LoRA endpoint via Ollama and return the translation.

    Raises on network/inference error — caller uses return_exceptions=True.
    """
    messages = stage1_messages(
        source_jp,
        notes=notes,
        glossary=glossary_context,
        rag_context=rag_context,
    )
    return await complete(
        settings.hime_qwen32b_url,
        settings.hime_qwen32b_model,
        messages,
    )
