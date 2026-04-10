"""
Stage 1 v2 public API.

Usage:
    from app.pipeline.stage1 import run_stage1, Stage1Drafts

    drafts = await run_stage1(
        segment="猫が走る。",
        rag_context="",
        glossary_context="",
    )
    print(drafts.qwen32b)   # "The cat runs."  (or None if adapter failed)
    print(drafts.jmdict)    # "cat run ."      (always a str)
"""
from ._types import Stage1Drafts
from .runner import run_stage1

__all__ = ["run_stage1", "Stage1Drafts"]
