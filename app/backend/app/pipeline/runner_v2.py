"""
runner_v2.py — Book-level pipeline v2 orchestrator.

Wires together:
  preprocessor → stage1 → stage2_merger → stage3_polish → stage4 (retry loop)
  → DB checkpoint per segment → epub_export on completion

The old runner.py stays for backward compat (single-paragraph /translate jobs).

WebSocket event contract:
  {"event": "preprocess_complete", "segment_count": N}
  {"event": "segment_start", "paragraph_id": id, "index": i, "total": N}
  {"event": "stage1_complete", "paragraph_id": id, "retry_kind"?: "full_retry"}
  {"event": "stage2_complete", "paragraph_id": id, "retry_kind"?: "full_retry"}
  {"event": "stage3_complete", "paragraph_id": id, "retry_kind"?: "fix_pass"|"full_retry",
                               "fix_pass_count"?: int, "full_retry_count"?: int}
  {"event": "stage4_verdict", "paragraph_id": id,
                              "verdict": "ok"|"fix_pass"|"full_retry",
                              "instruction": str,
                              "fix_pass_count": int, "full_retry_count": int}
  {"event": "segment_complete", "paragraph_id": id, "translation": text,
                                "retry_flag": bool}
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

# Stage 4 retry budgets (per segment, independent)
MAX_FIX_PASS_RETRIES = 2
MAX_FULL_PIPELINE_RETRIES = 1


def _augment_rag_with_retry(rag_context: str, instruction: str) -> str:
    """Append a retry instruction to rag_context as a clearly-labelled section.

    This is how the condensed segment instruction reaches Stage 1 on a full
    pipeline retry — without touching any adapter code.
    """
    if not instruction.strip():
        return rag_context
    note = f"[Retry instruction from prior review]: {instruction.strip()}"
    if rag_context.strip():
        return f"{rag_context}\n\n{note}"
    return note


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
    reviewer_notes: str | None = None,
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
        if reviewer_notes is not None:
            paragraph.reviewer_notes = reviewer_notes

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

            # Stage 4 — two-path retry dispatch
            fix_pass_count = 0
            full_retry_count = 0
            retry_flag_exhausted = False
            current_polished = polished_str
            current_merged = merged_str
            last_verdict: str = "ok"
            last_instruction: str = ""
            confidence_log: dict = {"cycles": []}

            while True:
                # Load + review + unload (reader)
                if dry_run:
                    reader = DryRunStage4Reader()
                    aggregator = DryRunStage4Aggregator()
                else:
                    reader = Stage4Reader()
                    aggregator = Stage4Aggregator()

                sentences = _SENT_SPLIT.split(current_polished.strip()) or [current_polished]
                source_sentences = _SENT_SPLIT.split(segment.source_jp.strip()) or [segment.source_jp]
                if len(source_sentences) < len(sentences):
                    source_sentences += [source_sentences[-1]] * (len(sentences) - len(source_sentences))
                source_sentences = source_sentences[: len(sentences)]

                reader.load(settings)
                annotations = await reader.review(
                    sentences=sentences, source_sentences=source_sentences,
                )
                reader.unload()

                aggregator.load(settings)
                segment_verdict = await aggregator.aggregate_segment(annotations)
                aggregator.unload()

                last_verdict = segment_verdict.verdict
                last_instruction = segment_verdict.instruction
                confidence_log["cycles"].append({
                    "verdict": segment_verdict.verdict,
                    "instruction": segment_verdict.instruction,
                    "fix_pass_count": fix_pass_count,
                    "full_retry_count": full_retry_count,
                })

                await ws_queue.put({
                    "event": "stage4_verdict",
                    "paragraph_id": paragraph_id,
                    "verdict": segment_verdict.verdict,
                    "instruction": segment_verdict.instruction,
                    "fix_pass_count": fix_pass_count,
                    "full_retry_count": full_retry_count,
                })

                if segment_verdict.verdict == "ok":
                    break

                if segment_verdict.verdict == "fix_pass":
                    if fix_pass_count >= MAX_FIX_PASS_RETRIES:
                        retry_flag_exhausted = True
                        _log.warning(
                            "[runner_v2] paragraph %d exhausted fix_pass budget (%d); "
                            "emitting anyway and setting retry_flag",
                            paragraph_id, MAX_FIX_PASS_RETRIES,
                        )
                        break
                    fix_pass_count += 1
                    # Stage 3 re-run with condensed instruction. Stage 3 manages its
                    # own VRAM (load/unload inside polish()); no external calls needed.
                    if dry_run:
                        current_polished = await dry_run_stage3_polish(
                            current_merged,
                            segment.glossary_context,
                            retry_instruction=segment_verdict.instruction,
                        )
                    else:
                        current_polished = await _stage3.polish(
                            current_merged,
                            segment.glossary_context,
                            retry_instruction=segment_verdict.instruction,
                        )
                    await ws_queue.put({
                        "event": "stage3_complete",
                        "paragraph_id": paragraph_id,
                        "retry_kind": "fix_pass",
                        "fix_pass_count": fix_pass_count,
                    })
                    continue

                if segment_verdict.verdict == "full_retry":
                    if full_retry_count >= MAX_FULL_PIPELINE_RETRIES:
                        retry_flag_exhausted = True
                        _log.warning(
                            "[runner_v2] paragraph %d exhausted full_retry budget (%d); "
                            "emitting anyway and setting retry_flag",
                            paragraph_id, MAX_FULL_PIPELINE_RETRIES,
                        )
                        break
                    full_retry_count += 1
                    # Inject the condensed instruction into rag_context; Stage 1
                    # adapters read rag_context verbatim, so this threads through
                    # all five adapters with zero adapter-internal changes.
                    augmented_rag = _augment_rag_with_retry(
                        segment.rag_context, segment_verdict.instruction,
                    )

                    # NOTE: The Stage 1 → 2 → 3 ladder below mirrors the initial pass
                    # earlier in the segment loop. If you change the initial ladder
                    # (field names, call signatures, event payloads), update this
                    # branch in lockstep.

                    # Stage 1 — full re-run with augmented context
                    if dry_run:
                        new_drafts = await make_dry_run_stage1_drafts(
                            segment=segment.source_jp,
                            rag_context=augmented_rag,
                            glossary_context=segment.glossary_context,
                        )
                    else:
                        new_drafts = await _stage1.run_stage1(
                            segment=segment.source_jp,
                            rag_context=augmented_rag,
                            glossary_context=segment.glossary_context,
                        )
                    await ws_queue.put({
                        "event": "stage1_complete",
                        "paragraph_id": paragraph_id,
                        "retry_kind": "full_retry",
                        "full_retry_count": full_retry_count,
                    })

                    new_drafts_dict: dict[str, str] = {
                        "qwen32b": new_drafts.qwen32b or "",
                        "translategemma": new_drafts.translategemma12b or "",
                        "qwen35_9b": new_drafts.qwen35_9b or "",
                        "gemma4_e4b": new_drafts.gemma4_e4b or "",
                        "jmdict": new_drafts.jmdict,
                    }

                    # Stage 2 — merge with same augmented rag_context
                    if dry_run:
                        current_merged = await dry_run_stage2_merge(
                            new_drafts_dict, augmented_rag, segment.glossary_context,
                        )
                    else:
                        current_merged = await _stage2.merge(
                            new_drafts_dict, augmented_rag, segment.glossary_context,
                        )
                    await ws_queue.put({
                        "event": "stage2_complete",
                        "paragraph_id": paragraph_id,
                        "retry_kind": "full_retry",
                        "full_retry_count": full_retry_count,
                    })

                    # Stage 3 — fresh polish, NO fix_pass retry_instruction because
                    # the instruction has already flowed through Stage 1 via rag_context.
                    if dry_run:
                        current_polished = await dry_run_stage3_polish(
                            current_merged, segment.glossary_context,
                        )
                    else:
                        current_polished = await _stage3.polish(
                            current_merged, segment.glossary_context,
                        )
                    await ws_queue.put({
                        "event": "stage3_complete",
                        "paragraph_id": paragraph_id,
                        "retry_kind": "full_retry",
                        "full_retry_count": full_retry_count,
                    })
                    continue

                # Defensive: unknown verdict → emit as-is
                _log.warning(
                    "[runner_v2] paragraph %d unknown verdict %r; emitting as-is",
                    paragraph_id, segment_verdict.verdict,
                )
                break

            reviewer_notes_text: str | None = None
            if retry_flag_exhausted:
                reviewer_notes_text = (
                    f"[Stage 4 retry budget exhausted] "
                    f"last_verdict={last_verdict} "
                    f"fix_pass_count={fix_pass_count}/{MAX_FIX_PASS_RETRIES} "
                    f"full_retry_count={full_retry_count}/{MAX_FULL_PIPELINE_RETRIES} "
                    f"last_instruction={last_instruction!r}"
                )

            final_text = current_polished
            await _checkpoint_segment(
                paragraph_id,
                final_text,
                confidence_log,
                retry_count_fix_pass=fix_pass_count,
                retry_count_full_pipeline=full_retry_count,
                retry_flag=retry_flag_exhausted,
                aggregator_verdict=last_verdict,
                aggregator_instruction=last_instruction,
                reviewer_notes=reviewer_notes_text,
            )

            await ws_queue.put({
                "event": "segment_complete",
                "paragraph_id": paragraph_id,
                "translation": final_text,
                "retry_flag": retry_flag_exhausted,
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
