"""Phase 7 — end-to-end dry-run test of the Stage 4 two-path retry mechanism.

Uses HIME_DRY_RUN=1 so no models are loaded. DryRunStage4Aggregator.aggregate_segment
is monkey-patched to emit a controlled verdict sequence, and we assert against the
real SQLite paragraphs row after the pipeline completes.
"""
from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.stage4_aggregator import SegmentVerdict


async def _seed_book(session, file_path: str) -> int:
    from app.models import Book, Chapter, Paragraph
    book = Book(
        title="e2e",
        file_path=file_path,
        total_chapters=1,
        total_paragraphs=1,
    )
    session.add(book)
    await session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=0,
        title="c1",
        total_paragraphs=1,
    )
    session.add(chapter)
    await session.flush()
    para = Paragraph(
        chapter_id=chapter.id,
        paragraph_index=0,
        source_text="彼女は静かに微笑んだ。",
    )
    session.add(para)
    await session.flush()
    await session.commit()
    return book.id


async def _get_paragraph(session, book_id: int):
    from sqlalchemy import select
    from app.models import Chapter, Paragraph
    stmt = (
        select(Paragraph)
        .join(Chapter, Paragraph.chapter_id == Chapter.id)
        .where(Chapter.book_id == book_id)
    )
    res = await session.execute(stmt)
    return res.scalars().first()


async def _drain(q: asyncio.Queue) -> list[dict]:
    events: list[dict] = []
    while True:
        item = await q.get()
        if item is None:
            break
        events.append(item)
    return events


@pytest.fixture(autouse=True)
def _enable_dry_run(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "hime_dry_run", True, raising=False)
    yield


def _patched_aggregator(verdicts: list[SegmentVerdict]):
    from app.pipeline.dry_run import DryRunStage4Aggregator
    verdicts_copy = list(verdicts)  # local copy so the outer list is not mutated

    async def fake_aggregate_segment(self, annotations):
        return (
            verdicts_copy.pop(0)
            if verdicts_copy
            else SegmentVerdict(verdict="ok", instruction="")
        )

    return patch.object(DryRunStage4Aggregator, "aggregate_segment", fake_aggregate_segment)


@pytest.mark.asyncio
async def test_e2e_fix_pass_persists_counter_to_sqlite(db_session):
    from app.pipeline.runner_v2 import run_pipeline_v2
    book_id = await _seed_book(db_session, "e2e_fix.epub")

    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="Tighten pacing."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with (
        _patched_aggregator(verdicts),
        patch("app.pipeline.runner_v2.export_book", AsyncMock(return_value="/tmp/e2e.epub")),
    ):
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=book_id, ws_queue=q, session=db_session)
        await _drain(q)

    # Expire cached state so the fresh DB row written by _checkpoint_segment
    # (which uses its own AsyncSessionLocal) is visible to our session.
    db_session.expire_all()
    para = await _get_paragraph(db_session, book_id)
    assert para is not None
    assert para.is_translated is True
    assert para.retry_count_fix_pass == 1
    assert para.retry_count_full_pipeline == 0
    assert para.retry_flag is False
    assert para.aggregator_verdict == "ok"


@pytest.mark.asyncio
async def test_e2e_full_retry_persists_counter_to_sqlite(db_session):
    from app.pipeline.runner_v2 import run_pipeline_v2
    book_id = await _seed_book(db_session, "e2e_full.epub")

    verdicts = [
        SegmentVerdict(verdict="full_retry", instruction="Speaker attribution wrong."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with (
        _patched_aggregator(verdicts),
        patch("app.pipeline.runner_v2.export_book", AsyncMock(return_value="/tmp/e2e.epub")),
    ):
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=book_id, ws_queue=q, session=db_session)
        await _drain(q)

    db_session.expire_all()
    para = await _get_paragraph(db_session, book_id)
    assert para is not None
    assert para.retry_count_fix_pass == 0
    assert para.retry_count_full_pipeline == 1
    assert para.retry_flag is False


@pytest.mark.asyncio
async def test_e2e_exhaustion_persists_retry_flag_and_reviewer_notes(db_session):
    from app.pipeline.runner_v2 import run_pipeline_v2
    book_id = await _seed_book(db_session, "e2e_exhaust.epub")

    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="A"),
        SegmentVerdict(verdict="fix_pass", instruction="B"),
        SegmentVerdict(verdict="fix_pass", instruction="C"),  # exhausted
    ]
    with (
        _patched_aggregator(verdicts),
        patch("app.pipeline.runner_v2.export_book", AsyncMock(return_value="/tmp/e2e.epub")),
    ):
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=book_id, ws_queue=q, session=db_session)
        await _drain(q)

    db_session.expire_all()
    para = await _get_paragraph(db_session, book_id)
    assert para is not None
    assert para.retry_count_fix_pass == 2
    assert para.retry_flag is True
    assert para.reviewer_notes is not None
    assert "retry budget exhausted" in para.reviewer_notes.lower()
    # Segment is still emitted (not blocked)
    assert para.is_translated is True
    assert para.translated_text is not None and para.translated_text.strip() != ""
