"""
runner_v2.py — Book-level pipeline v2 orchestrator.

Wires together:
  preprocessor → stage1 → stage2_merger → stage3_polish → stage4 (retry loop)
  → DB checkpoint per segment → epub_export on completion

The old runner.py stays for backward compat (single-paragraph /translate jobs).

WebSocket event contract:
  {"event": "preprocess_complete", "segment_count": N}
  {"event": "segment_start", "paragraph_id": id, "index": i, "total": N}
  {"event": "stage1_complete", "paragraph_id": id}
  {"event": "stage2_complete", "paragraph_id": id}
  {"event": "stage3_complete", "paragraph_id": id}
  {"event": "stage4_verdict", "paragraph_id": id, "verdict": "okay"|"retry", "retry_count": n}
  {"event": "segment_complete", "paragraph_id": id, "translation": text}
  {"event": "pipeline_complete", "epub_path": str}
  {"event": "pipeline_error", "detail": str}
  None  <- sentinel
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import AsyncSessionLocal
from ..models import Chapter, Paragraph, Translation
from ..services.epub_export_service import export_book
from . import preprocessor as _preprocessor
from . import stage1 as _stage1
from . import stage2_merger as _stage2
from . import stage3_polish as _stage3
from .stage4_aggregator import Stage4Aggregator
from .stage4_reader import Stage4Reader

_log = logging.getLogger(__name__)

MAX_STAGE4_RETRIES = 3


async def _checkpoint_segment(
    paragraph_id: int,
    final_text: str,
    confidence_log: dict | None,
    *,
    retry_count_fix_pass: int | None = None,
    retry_count_full_pipeline: int | None = None,
    retry_flag: bool | None = None,
    aggregator_verdict: str | None = None,
    aggregator_instruction: str | None = None,
) -> None:
    """Persist a completed segment translation using its own AsyncSessionLocal session."""
    async with AsyncSessionLocal() as session:
        paragraph = await session.get(Paragraph, paragraph_id)
        if paragraph is None:
            _log.warning("[runner_v2] Paragraph %d not found for checkpoint", paragraph_id)
            return

        paragraph.translated_text = final_text
        paragraph.is_translated = True
        paragraph.translated_at = datetime.now(UTC)

        if retry_count_fix_pass is not None:
            paragraph.retry_count_fix_pass = retry_count_fix_pass
        if retry_count_full_pipeline is not None:
            paragraph.retry_count_full_pipeline = retry_count_full_pipeline
        if retry_flag is not None:
            paragraph.retry_flag = retry_flag
        if aggregator_verdict is not None:
            paragraph.aggregator_verdict = aggregator_verdict
        if aggregator_instruction is not None:
            paragraph.aggregator_instruction = aggregator_instruction

        chapter = await session.get(Chapter, paragraph.chapter_id)
        if chapter:
            from sqlalchemy import select as _select
            res = await session.execute(
                _select(Paragraph).where(
                    Paragraph.chapter_id == chapter.id,
                    Paragraph.is_translated == True,  # noqa: E712
                )
            )
            chapter.translated_paragraphs = len(res.scalars().all())
            chapter.status = (
                "complete"
                if chapter.translated_paragraphs >= chapter.total_paragraphs
                else "in_progress"
            )

            from ..models import Book
            book = await session.get(Book, chapter.book_id)
            if book:
                from sqlalchemy import select as _sel
                res2 = await session.execute(
                    _sel(Paragraph)
                    .join(Chapter, Paragraph.chapter_id == Chapter.id)
                    .where(Chapter.book_id == book.id, Paragraph.is_translated == True)  # noqa: E712
                )
                book.translated_paragraphs = len(res2.scalars().all())
                book.status = (
                    "complete"
                    if book.translated_paragraphs >= book.total_paragraphs
                    else "in_progress"
                )

        # Try to create a Translation row for confidence logging
        try:
            from ..models import SourceText
            st = SourceText(
                title=f"para:{paragraph_id}",
                content=paragraph.source_text,
                language="ja",
            )
            session.add(st)
            await session.flush()
            translation = Translation(
                source_text_id=st.id,
                content=final_text,
                model="pipeline_v2",
                notes=f"paragraph:{paragraph_id}",
            )
            session.add(translation)
            await session.flush()
            if confidence_log is not None:
                translation.confidence_log = json.dumps(confidence_log)
        except Exception as exc:  # noqa: BLE001
            _log.warning("[runner_v2] Could not create Translation row: %s", exc)

        await session.commit()


async def run_pipeline_v2(
    book_id: int,
    ws_queue: asyncio.Queue,
    session: AsyncSession,
) -> None:
    """Full book-level pipeline v2 coroutine."""
    try:
        segments = await _preprocessor.preprocess_book(book_id, session)
        total = len(segments)
        await ws_queue.put({"event": "preprocess_complete", "segment_count": total})

        # Dry-run stubs (W8): when HIME_DRY_RUN=1, bypass all model loads.
        dry_run = bool(settings.hime_dry_run)
        if dry_run:
            from .dry_run import (  # noqa: PLC0415
                DryRunStage4Aggregator,
                DryRunStage4Reader,
                dry_run_stage2_merge,
                dry_run_stage3_polish,
                make_dry_run_stage1_drafts,
            )
            _log.info("[runner_v2] DRY-RUN mode active — no models will be loaded")

        _SENT_SPLIT = re.compile(r'(?<=[.!?…」])\s+')

        for i, segment in enumerate(segments):
            paragraph_id: int = segment.paragraph_id
            await ws_queue.put({
                "event": "segment_start",
                "paragraph_id": paragraph_id,
                "index": i,
                "total": total,
            })

            # Stage 1: pass fields from PreprocessedSegment
            if dry_run:
                drafts = await make_dry_run_stage1_drafts(
                    segment=segment.source_jp,
                    rag_context=segment.rag_context,
                    glossary_context=segment.glossary_context,
                )
            else:
                drafts = await _stage1.run_stage1(
                    segment=segment.source_jp,
                    rag_context=segment.rag_context,
                    glossary_context=segment.glossary_context,
                )
            await ws_queue.put({"event": "stage1_complete", "paragraph_id": paragraph_id})

            # Stage 2: convert Stage1Drafts to dict with keys matching merger_messages()
            drafts_dict: dict[str, str] = {
                "qwen32b": drafts.qwen32b or "",
                "translategemma": drafts.translategemma12b or "",
                "qwen35_9b": drafts.qwen35_9b or "",
                "gemma4_e4b": drafts.gemma4_e4b or "",
                "jmdict": drafts.jmdict,
            }
            if dry_run:
                merged_str = await dry_run_stage2_merge(drafts_dict, segment.rag_context, segment.glossary_context)
            else:
                merged_str = await _stage2.merge(drafts_dict, segment.rag_context, segment.glossary_context)
            await ws_queue.put({"event": "stage2_complete", "paragraph_id": paragraph_id})

            # Stage 3: polish(merged, glossary_context, retry_instruction="")
            if dry_run:
                polished_str = await dry_run_stage3_polish(merged_str, segment.glossary_context)
            else:
                polished_str = await _stage3.polish(merged_str, segment.glossary_context)
            await ws_queue.put({"event": "stage3_complete", "paragraph_id": paragraph_id})

            retry_count = 0
            current_polished = polished_str
            confidence_log: dict | None = None

            # Stage 4: Reader + Aggregator with retry loop
            if dry_run:
                reader = DryRunStage4Reader()
                aggregator = DryRunStage4Aggregator()
            else:
                reader = Stage4Reader()
                aggregator = Stage4Aggregator()
            reader.load(settings)
            aggregator.load(settings)

            sentences = _SENT_SPLIT.split(current_polished.strip()) or [current_polished]
            source_sentences = _SENT_SPLIT.split(segment.source_jp.strip()) or [segment.source_jp]
            if len(source_sentences) < len(sentences):
                source_sentences += [source_sentences[-1]] * (len(sentences) - len(source_sentences))
            source_sentences = source_sentences[: len(sentences)]

            while True:
                annotations = await reader.review(
                    sentences=sentences, source_sentences=source_sentences
                )

                # Aggregate per sentence group
                sorted_ann = sorted(annotations, key=lambda a: a.sentence_id)
                verdicts = []
                for sid, group in groupby(sorted_ann, key=lambda a: a.sentence_id):
                    verdict = await aggregator.aggregate(list(group))
                    verdicts.append(verdict)

                retry_verdicts = [v for v in verdicts if v.verdict == "retry"]
                # Build a combined verdict for the paragraph
                paragraph_verdict = "retry" if retry_verdicts else "okay"
                retry_instruction = (
                    " | ".join(
                        f"[s{getattr(v, 'sentence_id', '?')}] {v.retry_instruction}"
                        for v in retry_verdicts
                        if v.retry_instruction
                    )
                    if retry_verdicts
                    else ""
                )

                # Build confidence_log from verdicts
                confidence_log = {
                    "verdicts": [
                        {
                            "sentence_id": getattr(v, "sentence_id", None),
                            "verdict": v.verdict,
                            "confidence": getattr(v, "confidence", None),
                        }
                        for v in verdicts
                    ]
                }

                await ws_queue.put({
                    "event": "stage4_verdict",
                    "paragraph_id": paragraph_id,
                    "verdict": paragraph_verdict,
                    "retry_count": retry_count,
                })

                if paragraph_verdict == "retry" and retry_count < MAX_STAGE4_RETRIES:
                    retry_count += 1
                    reader.unload()
                    if dry_run:
                        current_polished = await dry_run_stage3_polish(
                            merged_str, segment.glossary_context, retry_instruction=retry_instruction
                        )
                    else:
                        current_polished = await _stage3.polish(
                            merged_str, segment.glossary_context, retry_instruction=retry_instruction
                        )
                    sentences = _SENT_SPLIT.split(current_polished.strip()) or [current_polished]
                    if len(source_sentences) < len(sentences):
                        source_sentences += [source_sentences[-1]] * (len(sentences) - len(source_sentences))
                    source_sentences = source_sentences[: len(sentences)]
                    reader.load(settings)
                else:
                    reader.unload()
                    break

            aggregator.unload()
            final_text = current_polished
            await _checkpoint_segment(paragraph_id, final_text, confidence_log)

            await ws_queue.put({
                "event": "segment_complete",
                "paragraph_id": paragraph_id,
                "translation": final_text,
            })

        epub_path = await export_book(book_id, session)
        await ws_queue.put({
            "event": "pipeline_complete",
            "epub_path": str(epub_path),
        })

    except Exception as exc:
        _log.exception("[runner_v2] Pipeline error for book %d", book_id)
        await ws_queue.put({"event": "pipeline_error", "detail": str(exc)})

    finally:
        await ws_queue.put(None)
