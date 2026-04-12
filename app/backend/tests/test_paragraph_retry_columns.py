"""Phase 2 — verify new retry-tracking columns on the paragraphs table."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_paragraph_model_has_retry_fields():
    from app.models import Paragraph
    for col in (
        "retry_count_fix_pass",
        "retry_count_full_pipeline",
        "retry_flag",
        "aggregator_verdict",
        "aggregator_instruction",
    ):
        assert hasattr(Paragraph, col), f"Paragraph is missing column {col}"


@pytest.mark.asyncio
async def test_paragraph_retry_defaults(db_session):
    from app.models import Book, Chapter, Paragraph

    book = Book(title="t", file_path="t.epub")
    db_session.add(book)
    await db_session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=0, title="c")
    db_session.add(chapter)
    await db_session.flush()
    para = Paragraph(chapter_id=chapter.id, paragraph_index=0, source_text="x")
    db_session.add(para)
    await db_session.flush()
    await db_session.refresh(para)

    assert para.retry_count_fix_pass == 0
    assert para.retry_count_full_pipeline == 0
    assert para.retry_flag is False
    assert para.aggregator_verdict is None
    assert para.aggregator_instruction is None


@pytest.mark.asyncio
async def test_retry_columns_exist_in_schema(db_session):
    """Verify all 5 Stage 4 retry-tracking columns are present in the paragraphs table.

    Note: this test runs against a fresh SQLite created by create_all(), so it
    verifies ORM schema completeness, NOT the ALTER TABLE migration path.
    The ALTER TABLE path in _V200_PARAGRAPH_RETRY_COLS is exercised by a
    pre-existing DB, which this test does not simulate.
    """
    rows = (await db_session.execute(text("PRAGMA table_info(paragraphs)"))).fetchall()
    existing = {r[1] for r in rows}
    for col in (
        "retry_count_fix_pass",
        "retry_count_full_pipeline",
        "retry_flag",
        "aggregator_verdict",
        "aggregator_instruction",
    ):
        assert col in existing, f"paragraphs table is missing column {col}"
