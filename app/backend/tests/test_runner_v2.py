"""
Tests for pipeline v2 runner orchestrator and EPUB export service.
All stage modules are mocked — no actual model inference required.
DB operations use in-memory SQLite async engine.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Book, Chapter, Paragraph


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_book(async_session):
    book = Book(
        title="Test Novel",
        author="Author A",
        file_path="/fake/test.epub",
        total_chapters=1,
        total_paragraphs=1,
    )
    async_session.add(book)
    await async_session.flush()

    chapter = Chapter(
        book_id=book.id,
        chapter_index=0,
        title="Chapter 1",
        total_paragraphs=1,
    )
    async_session.add(chapter)
    await async_session.flush()

    paragraph = Paragraph(
        chapter_id=chapter.id,
        paragraph_index=0,
        source_text="彼女は微笑んだ。",
    )
    async_session.add(paragraph)
    await async_session.commit()

    return {"book_id": book.id, "chapter_id": chapter.id, "paragraph_id": paragraph.id}


def _make_segment(paragraph_id: int, text: str = "彼女は微笑んだ。"):
    return SimpleNamespace(
        paragraph_id=paragraph_id,
        source_jp=text,
        source_text=text,  # kept for compatibility
        rag_context="",
        glossary_context="",
    )


def _make_verdict(verdict: str, retry_instruction: str = "Fix tone.", confidence: dict | None = None):
    return SimpleNamespace(
        verdict=verdict,
        retry_instruction=retry_instruction,
        confidence=confidence or {"score": 0.8},
    )


async def _drain_queue(q: asyncio.Queue) -> list[dict]:
    events = []
    while True:
        item = await asyncio.wait_for(q.get(), timeout=2.0)
        if item is None:
            break
        events.append(item)
    return events


@pytest.mark.asyncio
async def test_preprocess_complete_event(seeded_book, async_session):
    paragraph_id = seeded_book["paragraph_id"]
    fake_segment = _make_segment(paragraph_id)
    fake_verdict = _make_verdict("okay")

    with (
        patch("app.pipeline.runner_v2._preprocessor") as mock_pre,
        patch("app.pipeline.runner_v2._stage1") as mock_s1,
        patch("app.pipeline.runner_v2._stage2") as mock_s2,
        patch("app.pipeline.runner_v2._stage3") as mock_s3,
        patch("app.pipeline.runner_v2.Stage4Reader") as MockReader,
        patch("app.pipeline.runner_v2.Stage4Aggregator") as MockAgg,
        patch("app.pipeline.runner_v2.export_book", new_callable=AsyncMock) as mock_export,
        patch("app.pipeline.runner_v2._checkpoint_segment", new_callable=AsyncMock),
    ):
        mock_pre.preprocess_book = AsyncMock(return_value=[fake_segment])
        mock_s1.run_stage1 = AsyncMock(return_value=MagicMock())
        mock_s2.merge = AsyncMock(return_value="merged text")
        mock_s3.polish = AsyncMock(return_value="polished text")
        mock_reader_instance = MagicMock()
        mock_reader_instance.review = AsyncMock(return_value=[MagicMock(sentence_id=0)])
        mock_reader_instance.load = MagicMock()
        mock_reader_instance.unload = MagicMock()
        MockReader.return_value = mock_reader_instance
        mock_agg_instance = MagicMock()
        mock_agg_instance.aggregate = AsyncMock(return_value=fake_verdict)
        mock_agg_instance.load = MagicMock()
        mock_agg_instance.unload = MagicMock()
        MockAgg.return_value = mock_agg_instance
        mock_export.return_value = Path("/fake/exports/1_translated.epub")

        from app.pipeline.runner_v2 import run_pipeline_v2
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(seeded_book["book_id"], q, async_session)
        events = await _drain_queue(q)

    event_types = [e["event"] for e in events]
    assert "preprocess_complete" in event_types
    pre_event = next(e for e in events if e["event"] == "preprocess_complete")
    assert pre_event["segment_count"] == 1


@pytest.mark.asyncio
async def test_retry_loop_repolished_twice(seeded_book, async_session):
    paragraph_id = seeded_book["paragraph_id"]
    fake_segment = _make_segment(paragraph_id)
    verdicts = [
        _make_verdict("retry", "Fix tone."),
        _make_verdict("retry", "Fix register."),
        _make_verdict("okay"),
    ]
    verdict_iter = iter(verdicts)

    with (
        patch("app.pipeline.runner_v2._preprocessor") as mock_pre,
        patch("app.pipeline.runner_v2._stage1") as mock_s1,
        patch("app.pipeline.runner_v2._stage2") as mock_s2,
        patch("app.pipeline.runner_v2._stage3") as mock_s3,
        patch("app.pipeline.runner_v2.Stage4Reader") as MockReader,
        patch("app.pipeline.runner_v2.Stage4Aggregator") as MockAgg,
        patch("app.pipeline.runner_v2.export_book", new_callable=AsyncMock) as mock_export,
        patch("app.pipeline.runner_v2._checkpoint_segment", new_callable=AsyncMock),
    ):
        mock_pre.preprocess_book = AsyncMock(return_value=[fake_segment])
        mock_s1.run_stage1 = AsyncMock(return_value=MagicMock())
        mock_s2.merge = AsyncMock(return_value="merged text")
        mock_s3.polish = AsyncMock(side_effect=["polished v1", "polished v2", "polished v3"])
        mock_reader_instance = MagicMock()
        mock_reader_instance.review = AsyncMock(return_value=[MagicMock(sentence_id=0)])
        mock_reader_instance.load = MagicMock()
        mock_reader_instance.unload = MagicMock()
        MockReader.return_value = mock_reader_instance
        mock_agg_instance = MagicMock()
        mock_agg_instance.aggregate = AsyncMock(side_effect=lambda _anns: next(verdict_iter))
        mock_agg_instance.load = MagicMock()
        mock_agg_instance.unload = MagicMock()
        MockAgg.return_value = mock_agg_instance
        mock_export.return_value = Path("/fake/exports/1_translated.epub")

        from app.pipeline.runner_v2 import run_pipeline_v2
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(seeded_book["book_id"], q, async_session)
        await _drain_queue(q)

    assert mock_s3.polish.call_count == 3


@pytest.mark.asyncio
async def test_retry_cap_accepts_after_3(seeded_book, async_session):
    paragraph_id = seeded_book["paragraph_id"]
    fake_segment = _make_segment(paragraph_id)
    always_retry = _make_verdict("retry", "Still not great.")

    polish_call_count = 0

    async def counting_polish(*args, **kwargs):
        nonlocal polish_call_count
        polish_call_count += 1
        return f"polished v{polish_call_count}"

    with (
        patch("app.pipeline.runner_v2._preprocessor") as mock_pre,
        patch("app.pipeline.runner_v2._stage1") as mock_s1,
        patch("app.pipeline.runner_v2._stage2") as mock_s2,
        patch("app.pipeline.runner_v2._stage3") as mock_s3,
        patch("app.pipeline.runner_v2.Stage4Reader") as MockReader,
        patch("app.pipeline.runner_v2.Stage4Aggregator") as MockAgg,
        patch("app.pipeline.runner_v2.export_book", new_callable=AsyncMock) as mock_export,
        patch("app.pipeline.runner_v2._checkpoint_segment", new_callable=AsyncMock),
    ):
        mock_pre.preprocess_book = AsyncMock(return_value=[fake_segment])
        mock_s1.run_stage1 = AsyncMock(return_value=MagicMock())
        mock_s2.merge = AsyncMock(return_value="merged text")
        mock_s3.polish = AsyncMock(side_effect=counting_polish)
        mock_reader_instance = MagicMock()
        mock_reader_instance.review = AsyncMock(return_value=[MagicMock(sentence_id=0)])
        mock_reader_instance.load = MagicMock()
        mock_reader_instance.unload = MagicMock()
        MockReader.return_value = mock_reader_instance
        mock_agg_instance = MagicMock()
        mock_agg_instance.aggregate = AsyncMock(return_value=always_retry)
        mock_agg_instance.load = MagicMock()
        mock_agg_instance.unload = MagicMock()
        MockAgg.return_value = mock_agg_instance
        mock_export.return_value = Path("/fake/exports/1_translated.epub")

        from app.pipeline.runner_v2 import run_pipeline_v2
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(seeded_book["book_id"], q, async_session)
        events = await _drain_queue(q)

    # 1 initial + 3 retries = 4 total
    assert polish_call_count == 4
    event_types = [e["event"] for e in events]
    assert "pipeline_complete" in event_types
    assert "pipeline_error" not in event_types
    verdict_events = [e for e in events if e["event"] == "stage4_verdict"]
    assert len(verdict_events) == 4
    assert all(e["verdict"] == "retry" for e in verdict_events)


@pytest.mark.asyncio
async def test_db_checkpoint_written(seeded_book, async_session):
    paragraph_id = seeded_book["paragraph_id"]
    fake_segment = _make_segment(paragraph_id)
    fake_verdict = _make_verdict("okay", confidence={"score": 0.95})

    checkpoint_calls = []

    async def fake_checkpoint(pid, text, confidence):
        checkpoint_calls.append({"paragraph_id": pid, "text": text, "confidence": confidence})

    with (
        patch("app.pipeline.runner_v2._preprocessor") as mock_pre,
        patch("app.pipeline.runner_v2._stage1") as mock_s1,
        patch("app.pipeline.runner_v2._stage2") as mock_s2,
        patch("app.pipeline.runner_v2._stage3") as mock_s3,
        patch("app.pipeline.runner_v2.Stage4Reader") as MockReader,
        patch("app.pipeline.runner_v2.Stage4Aggregator") as MockAgg,
        patch("app.pipeline.runner_v2.export_book", new_callable=AsyncMock) as mock_export,
        patch("app.pipeline.runner_v2._checkpoint_segment", side_effect=fake_checkpoint),
    ):
        mock_pre.preprocess_book = AsyncMock(return_value=[fake_segment])
        mock_s1.run_stage1 = AsyncMock(return_value=MagicMock())
        mock_s2.merge = AsyncMock(return_value="merged text")
        mock_s3.polish = AsyncMock(return_value="polished text")
        mock_reader_instance = MagicMock()
        mock_reader_instance.review = AsyncMock(return_value=[MagicMock(sentence_id=0)])
        mock_reader_instance.load = MagicMock()
        mock_reader_instance.unload = MagicMock()
        MockReader.return_value = mock_reader_instance
        mock_agg_instance = MagicMock()
        mock_agg_instance.aggregate = AsyncMock(return_value=fake_verdict)
        mock_agg_instance.load = MagicMock()
        mock_agg_instance.unload = MagicMock()
        MockAgg.return_value = mock_agg_instance
        mock_export.return_value = Path("/fake/exports/1_translated.epub")

        from app.pipeline.runner_v2 import run_pipeline_v2
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(seeded_book["book_id"], q, async_session)
        await _drain_queue(q)

    assert len(checkpoint_calls) == 1
    call = checkpoint_calls[0]
    assert call["paragraph_id"] == paragraph_id
    assert call["text"] == "polished text"
    # confidence_log is now a dict built from verdicts list
    assert isinstance(call["confidence"], dict)
    assert "verdicts" in call["confidence"]


@pytest.mark.asyncio
async def test_export_book_creates_file(async_session, tmp_path):
    book = Book(
        title="Export Test Novel",
        author="Author B",
        file_path="/fake/export_test.epub",
        total_chapters=1,
        total_paragraphs=1,
        translated_paragraphs=1,
        status="complete",
    )
    async_session.add(book)
    await async_session.flush()

    chapter = Chapter(
        book_id=book.id,
        chapter_index=0,
        title="Chapter One",
        total_paragraphs=1,
        translated_paragraphs=1,
        status="complete",
    )
    async_session.add(chapter)
    await async_session.flush()

    paragraph = Paragraph(
        chapter_id=chapter.id,
        paragraph_index=0,
        source_text="彼女は微笑んだ。",
        translated_text="She smiled.",
        is_translated=True,
    )
    async_session.add(paragraph)
    await async_session.commit()

    expected_path = tmp_path / f"{book.id}_translated.epub"

    with (
        patch("app.services.epub_export_service.EXPORTS_DIR", tmp_path),
        patch("app.services.epub_export_service.asyncio.to_thread") as mock_thread,
    ):
        async def fake_to_thread(fn, *args, **kwargs):
            path = args[-1]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fake-epub-content")
        mock_thread.side_effect = fake_to_thread

        from app.services.epub_export_service import export_book
        result_path = await export_book(book.id, async_session)

    assert result_path == expected_path
    assert result_path.exists()
    assert result_path.read_bytes() == b"fake-epub-content"


def test_reassemble_chapter_format():
    from app.pipeline.postprocessor import reassemble_chapter
    paras = [(0, "She smiled."), (1, "The room was quiet.")]
    result = reassemble_chapter(paras, "Chapter 1")
    lines = result.split("\n\n")
    assert lines[0] == "Chapter 1"
    assert lines[1] == ""
    assert "She smiled." in result
    assert "The room was quiet." in result


@pytest.mark.asyncio
async def test_postprocess_book_fallback(async_session):
    book = Book(
        title="Fallback Test",
        author=None,
        file_path="/fake/fallback.epub",
        total_chapters=1,
        total_paragraphs=1,
    )
    async_session.add(book)
    await async_session.flush()

    chapter = Chapter(
        book_id=book.id,
        chapter_index=0,
        title="Intro",
        total_paragraphs=1,
    )
    async_session.add(chapter)
    await async_session.flush()

    paragraph = Paragraph(
        chapter_id=chapter.id,
        paragraph_index=0,
        source_text="これはテストです。",
        translated_text=None,
        is_translated=False,
    )
    async_session.add(paragraph)
    await async_session.commit()

    from app.pipeline.postprocessor import postprocess_book
    result = await postprocess_book(book.id, async_session)

    assert chapter.id in result
    assert "[untranslated:" in result[chapter.id]
    assert "これはテストです。" in result[chapter.id]
