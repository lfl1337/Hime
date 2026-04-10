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
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models import Chapter, Paragraph, Translation
from ..services.epub_export_service import export_book
from . import preprocessor as _preprocessor
from . import stage1 as _stage1
from . import stage2_merger as _stage2
from . import stage3_polish as _stage3
from . import stage4_aggregator as _stage4_agg
from . import stage4_reader as _stage4_reader

_log = logging.getLogger(__name__)

MAX_STAGE4_RETRIES = 3


async def _checkpoint_segment(
    paragraph_id: int,
    final_text: str,
    confidence_log: dict | None,
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

        chapter = await session.get(Chapter, paragraph.chapter_id)
        if chapter:
            from sqlalchemy import select as _select
            res = await session.execute(
                _select(Paragraph).where(
                    Paragraph.chapter_id == chapter.id,
                    Paragraph.is_translated == True,  # noqa: E712
                )
            )
            chapter.translated_paragraphs = len(res.scalars().all()) + 1
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
                book.translated_paragraphs = len(res2.scalars().all()) + 1
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

        for i, segment in enumerate(segments):
            paragraph_id: int = segment.paragraph_id
            await ws_queue.put({
                "event": "segment_start",
                "paragraph_id": paragraph_id,
                "index": i,
                "total": total,
            })

            drafts = await _stage1.run_stage1(segment, session)
            await ws_queue.put({"event": "stage1_complete", "paragraph_id": paragraph_id})

            merged_str = await _stage2.merge(drafts, session)
            await ws_queue.put({"event": "stage2_complete", "paragraph_id": paragraph_id})

            polished_str = await _stage3.polish(merged_str, session)
            await ws_queue.put({"event": "stage3_complete", "paragraph_id": paragraph_id})

            retry_count = 0
            current_polished = polished_str
            confidence_log: dict | None = None

            while True:
                annotations = await _stage4_reader.review(current_polished, session)
                verdict_obj = await _stage4_agg.aggregate(annotations)
                confidence_log = getattr(verdict_obj, "confidence", None)

                await ws_queue.put({
                    "event": "stage4_verdict",
                    "paragraph_id": paragraph_id,
                    "verdict": verdict_obj.verdict,
                    "retry_count": retry_count,
                })

                if verdict_obj.verdict == "retry" and retry_count < MAX_STAGE4_RETRIES:
                    retry_count += 1
                    retry_instruction = getattr(verdict_obj, "retry_instruction", "") or ""
                    current_polished = await _stage3.polish(
                        merged_str, session, retry_instruction=retry_instruction
                    )
                else:
                    break

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
