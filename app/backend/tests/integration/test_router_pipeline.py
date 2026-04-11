"""Integration tests for /api/v1/pipeline router.

Router: app/routers/pipeline.py
Prefix: /api/v1/pipeline
Endpoints tested:
  POST /api/v1/pipeline/{book_id}/preprocess  — book not found → 404
  POST /api/v1/pipeline/{book_id}/preprocess  — real book with dry-run → 200
"""
import pytest

from app.config import settings as _settings
from app.database import AsyncSessionLocal
from app.models import Book, Chapter, Paragraph


def test_preprocess_404_on_missing_book(test_client):
    """POST /api/v1/pipeline/999999/preprocess should return 404 for unknown book."""
    response = test_client.post("/api/v1/pipeline/999999/preprocess")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_preprocess_book_with_paragraphs(test_client, monkeypatch):
    """POST /api/v1/pipeline/{book_id}/preprocess returns 200 with a real book."""
    monkeypatch.setattr(_settings, "hime_dry_run", True)

    # Insert minimal book data
    async with AsyncSessionLocal() as session:
        book = Book(
            title="Integration Test Book",
            author="Test",
            file_path="integration-test-preprocess.epub",
            total_paragraphs=1,
            translated_paragraphs=0,
            status="pending",
        )
        session.add(book)
        await session.flush()
        chapter = Chapter(
            book_id=book.id,
            chapter_index=0,
            title="統合テスト章",
            total_paragraphs=1,
            translated_paragraphs=0,
            status="pending",
        )
        session.add(chapter)
        await session.flush()
        session.add(Paragraph(
            chapter_id=chapter.id,
            paragraph_index=0,
            source_text="これは統合テスト用の文章です。",
            is_translated=False,
        ))
        await session.commit()
        book_id = book.id

    response = test_client.post(f"/api/v1/pipeline/{book_id}/preprocess")
    assert response.status_code == 200
    body = response.json()
    assert body["book_id"] == book_id
    assert body["segment_count"] >= 1
    assert isinstance(body["sample"], list)
