"""
Shared dataclass for Stage 1 v2 pipeline outputs.

All adapter fields are Optional — an adapter that fails or is unavailable
sets its field to None. `jmdict` is the exception: LexiconService always
succeeds (it may return an empty string for unknown input, but never raises).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Stage1Drafts:
    source_jp: str
    jmdict: str
    qwen32b: str | None = field(default=None)            # 1A — Ollama Qwen2.5-32B LoRA
    translategemma12b: str | None = field(default=None)  # 1B — TranslateGemma-12B (Unsloth)
    qwen35_9b: str | None = field(default=None)          # 1C — Qwen3.5-9B non-thinking (Unsloth)
    llm_jp: str | None = field(default=None)             # 1D — LLM-jp-3-7.2B-Instruct3 (NF4 4-bit)
