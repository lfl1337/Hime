"""
RAG indexer: build a per-series sqlite-vec store from a finished book.

Idempotent: re-running with the same book_id only inserts new (unique-by-paragraph_id)
chunks. After indexing, automatically syncs the Obsidian vault.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from ..core.paths import RAG_DIR
from ..database import AsyncSessionLocal
from ..models import Book, Chapter, Paragraph
from .chunker import chunk_paragraph_pairs
from .embeddings import embed_texts
from .store import SeriesStore

_log = logging.getLogger(__name__)


async def build_for_book(book_id: int) -> int:
    """Index a single book into its series store. Returns count of new chunks added."""
    async with AsyncSessionLocal() as session:
        book = await session.get(Book, book_id)
        if book is None:
            _log.warning("[rag] book %d not found", book_id)
            return 0
        if book.series_id is None:
            _log.warning("[rag] book %d has no series_id; skipping", book_id)
            return 0

        result = await session.execute(
            select(Paragraph, Chapter)
            .join(Chapter, Paragraph.chapter_id == Chapter.id)
            .where(Chapter.book_id == book_id)
            .where(Paragraph.is_reviewed == True)  # noqa: E712
            .order_by(Paragraph.paragraph_index)
        )
        pairs: list[dict] = []
        series_id = book.series_id
        for paragraph, chapter in result.all():
            pairs.append({
                "book_id": book_id,
                "chapter_id": chapter.id,
                "paragraph_id": paragraph.id,
                "source_text": paragraph.source_text,
                "translated_text": paragraph.translated_text or "",
            })

    chunks = chunk_paragraph_pairs(pairs)
    if not chunks:
        return 0

    embeddings = embed_texts([f"{c.source_text}\n{c.translated_text}" for c in chunks])

    db_path = RAG_DIR / f"series_{series_id}.db"
    store = SeriesStore(db_path)
    store.initialize()
    before = store.count()
    store.insert_chunks(chunks, embeddings)
    after = store.count()
    store.close()

    new_count = after - before

    # Auto-sync Obsidian vault after indexing
    if new_count > 0:
        try:
            from .vault_exporter import sync_series
            sync_series(series_id=series_id)
        except Exception as e:  # noqa: BLE001
            _log.warning("[rag] vault sync failed for series %d: %s", series_id, e)

    return new_count
