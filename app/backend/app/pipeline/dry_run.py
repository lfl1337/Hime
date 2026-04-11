"""
Pipeline v2 dry-run stubs.

Every real model class gets a DryRunModel counterpart that implements the
same interface (load / unload / generate / review / aggregate) but performs
no VRAM allocation and returns deterministic fake output. Used by tests
and UI verification runs triggered with HIME_DRY_RUN=1.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any

# Import the types from the real pipeline modules.
from .stage1._types import Stage1Drafts
from .stage4_aggregator import AggregatorVerdict, SegmentVerdict
from .stage4_reader import PERSONAS, PersonaAnnotation


class DryRunModel:
    """Generic dry-run stub matching the load/unload/generate surface of real models."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.loaded = False

    def load(self, settings: Any) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def generate(self, prompt: str) -> str:
        digest = hashlib.sha1(prompt.encode("utf-8", "ignore")).hexdigest()[:8]
        snippet = prompt[:40].replace("\n", " ")
        return f"[DRY-RUN {self.name}] {digest} {snippet}"


# --- Stage 1 -----------------------------------------------------------------

async def make_dry_run_stage1_drafts(
    *,
    segment: str,
    rag_context: str,
    glossary_context: str,
) -> Stage1Drafts:
    """Produce deterministic Stage1Drafts without loading any Stage 1 model."""
    _ = rag_context, glossary_context
    digest = hashlib.sha1(segment.encode("utf-8", "ignore")).hexdigest()[:8]
    snippet = segment[:30].replace("\n", " ")

    def stamp(tag: str) -> str:
        return f"[DRY-RUN stage1/{tag}:{digest}] {snippet}"

    return Stage1Drafts(
        source_jp=segment,
        jmdict="[DRY-RUN jmdict] no terms",
        qwen32b=stamp("qwen32b"),
        translategemma12b=stamp("translategemma"),
        qwen35_9b=stamp("qwen35_9b"),
        gemma4_e4b=stamp("gemma4_e4b"),
    )


# --- Stage 2 / Stage 3 -------------------------------------------------------

async def dry_run_stage2_merge(
    drafts: dict[str, Any],
    rag_context: str,
    glossary_context: str,
) -> str:
    """Deterministic stage 2 merge without loading TranslateGemma-27B."""
    _ = rag_context, glossary_context
    base = drafts.get("qwen32b") or next((v for v in drafts.values() if isinstance(v, str) and v), "")
    digest = hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:8]
    return f"[DRY-RUN stage2:{digest}] {base[:40]}"


async def dry_run_stage3_polish(
    merged: str,
    glossary_context: str,
    retry_instruction: str = "",
) -> str:
    """Deterministic stage 3 polish without loading Qwen3-30B-A3B."""
    _ = glossary_context
    retry_suffix = f" retry={retry_instruction[:20]}" if retry_instruction else ""
    digest = hashlib.sha1((merged + retry_instruction).encode("utf-8", "ignore")).hexdigest()[:8]
    return f"[DRY-RUN stage3:{digest}]{retry_suffix} {merged[:40]}"


# --- Stage 4 -----------------------------------------------------------------

class DryRunStage4Reader:
    """Dry-run counterpart of Stage4Reader — 15 persona annotations per sentence, no VRAM."""

    def __init__(self) -> None:
        self.loaded = False

    def load(self, settings: Any) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    async def review(
        self,
        *,
        sentences: list[str],
        source_sentences: list[str],
    ) -> list[PersonaAnnotation]:
        await asyncio.sleep(0)
        out: list[PersonaAnnotation] = []
        for sid, (translation, _source) in enumerate(zip(sentences, source_sentences)):
            digest = hashlib.sha1(translation.encode("utf-8", "ignore")).hexdigest()[:8]
            for persona_name, _focus in PERSONAS:
                out.append(PersonaAnnotation(
                    persona=persona_name,
                    sentence_id=sid,
                    rating=0.80,
                    issues=[],
                    suggestion=f"[DRY-RUN {persona_name}:{digest}]",
                ))
        return out


class DryRunStage4Aggregator:
    """Dry-run counterpart of Stage4Aggregator — always returns 'okay'."""

    def __init__(self) -> None:
        self.loaded = False

    def load(self, settings: Any) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    async def aggregate(self, annotations: list[PersonaAnnotation]) -> AggregatorVerdict:
        await asyncio.sleep(0)
        sentence_id = annotations[0].sentence_id if annotations else 0
        return AggregatorVerdict(
            sentence_id=sentence_id,
            verdict="okay",
            retry_instruction=None,
            confidence=0.80,
        )

    async def aggregate_segment(self, annotations: list[PersonaAnnotation]) -> SegmentVerdict:
        await asyncio.sleep(0)
        return SegmentVerdict(verdict="ok", instruction="")


def make_dry_run_stage4_reader() -> DryRunStage4Reader:
    return DryRunStage4Reader()


def make_dry_run_stage4_aggregator() -> DryRunStage4Aggregator:
    return DryRunStage4Aggregator()
