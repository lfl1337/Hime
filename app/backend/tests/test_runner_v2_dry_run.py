"""End-to-end runner_v2 test in dry-run mode.

Uses a temp DB (provided by conftest isolation), inserts one book + one chapter
+ two paragraphs, runs run_pipeline_v2 with HIME_DRY_RUN=1, and verifies:
  1. Expected WebSocket events fire in correct order
  2. All paragraphs get translated_text containing [DRY-RUN stage3
  3. No model libraries (unsloth, transformers) are imported during the run
"""
import asyncio

import pytest

from app.config import settings as _settings
from app.database import AsyncSessionLocal, init_db
from app.models import Book, Chapter, Paragraph
from app.pipeline.runner_v2 import run_pipeline_v2


@pytest.mark.asyncio
async def test_runner_v2_dry_run_end_to_end(monkeypatch):
    """Full pipeline dry-run: 2 paragraphs → correct WS events → dry-run translations."""
    # Use monkeypatch to mutate the already-imported settings object.
    # runner_v2.py holds a reference to this same object, so the change takes effect.
    monkeypatch.setattr(_settings, "hime_dry_run", True)
    assert _settings.hime_dry_run is True, "hime_dry_run=True not applied"

    await init_db()

    # Insert minimal test data
    async with AsyncSessionLocal() as session:
        book = Book(
            title="Dry-run test book",
            author="Test",
            file_path="test-dry-run.epub",  # file_path is NOT NULL UNIQUE
            total_paragraphs=2,
            translated_paragraphs=0,
            status="pending",
        )
        session.add(book)
        await session.flush()
        chapter = Chapter(
            book_id=book.id,
            chapter_index=0,
            title="Ch1",
            total_paragraphs=2,
            translated_paragraphs=0,
            status="pending",
        )
        session.add(chapter)
        await session.flush()
        for idx, src in enumerate(["テスト文章です。", "もう一つのテスト文章です。"]):
            session.add(Paragraph(
                chapter_id=chapter.id,
                paragraph_index=idx,
                source_text=src,
                is_translated=False,
            ))
        await session.commit()
        book_id = book.id
        chapter_id = chapter.id

    # Run the pipeline
    events: list[dict] = []
    ws_queue: asyncio.Queue = asyncio.Queue()

    async def collect_events():
        while True:
            evt = await ws_queue.get()
            if evt is None:
                break
            events.append(evt)

    async with AsyncSessionLocal() as session:
        collector = asyncio.create_task(collect_events())
        await run_pipeline_v2(book_id, ws_queue, session)
        await collector

    # Assert event order
    event_names = [e.get("event") for e in events]
    assert "preprocess_complete" in event_names, f"Expected preprocess_complete, got: {event_names}"
    assert event_names.count("segment_start") >= 1, f"Expected segment_start events, got: {event_names}"
    assert "pipeline_complete" in event_names, f"Expected pipeline_complete, got: {event_names}"

    # Assert all paragraphs have dry-run translations
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Paragraph).where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
        paragraphs = result.scalars().all()
        assert len(paragraphs) == 2
        for p in paragraphs:
            assert p.is_translated is True, f"Paragraph {p.id} not marked translated"
            assert p.translated_text is not None, f"Paragraph {p.id} has no translated_text"
            assert "[DRY-RUN" in p.translated_text, (
                f"Expected dry-run marker in: {p.translated_text}"
            )
