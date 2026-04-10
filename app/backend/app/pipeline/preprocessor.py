"""
Pipeline v2 — Pre-Processing stage (WS-A).

Converts a Book's Paragraph records (already in SQLite from EPUB import) into
PreprocessedSegment objects that carry:
  - MeCab token list (from LexiconService)
  - Glossary context string (from GlossaryService)
  - RAG context string (from RAG retriever, series-scoped)

The resulting list is consumed by Stage 1 translators.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Book, Chapter, Paragraph
from ..rag.embeddings import embed_texts
from ..rag.retriever import format_rag_context
from ..rag.store import SeriesStore
from ..core.paths import RAG_DIR
from ..services.glossary_service import GlossaryService
from ..services.lexicon_service import LexiconService, LexiconToken

_log = logging.getLogger(__name__)


@dataclass
class PreprocessedSegment:
    """One paragraph ready for Stage 1 translation."""
    paragraph_id: int
    source_jp: str
    mecab_tokens: list[LexiconToken]
    glossary_context: str
    rag_context: str


async def preprocess_book(
    book_id: int,
    session: AsyncSession,
    rag_top_k: int = 5,
) -> list[PreprocessedSegment]:
    """
    Load all Paragraphs for *book_id* and enrich each one with:
      - MeCab tokens via LexiconService
      - Glossary context via GlossaryService
      - RAG context via SeriesStore (skipped when series_id is None or store absent)

    Parameters
    ----------
    book_id:
        Primary key of the Book record.
    session:
        Active async SQLAlchemy session (caller-owned, not committed here).
    rag_top_k:
        How many RAG chunks to retrieve per paragraph (default 5).

    Returns
    -------
    list[PreprocessedSegment]
        One entry per non-skipped Paragraph, ordered by chapter_index then
        paragraph_index.

    Raises
    ------
    ValueError
        If no Book with *book_id* exists.
    """
    # ── 1. Load Book ──────────────────────────────────────────────────────
    book: Book | None = await session.get(Book, book_id)
    if book is None:
        raise ValueError(f"Book {book_id} not found")

    # ── 2. Load Paragraphs ordered by chapter + position ──────────────────
    stmt = (
        select(Paragraph)
        .join(Chapter, Paragraph.chapter_id == Chapter.id)
        .where(Chapter.book_id == book_id)
        .where(Paragraph.is_skipped == False)  # noqa: E712
        .order_by(Chapter.chapter_index, Paragraph.paragraph_index)
    )
    result = await session.execute(stmt)
    paragraphs: list[Paragraph] = list(result.scalars().all())

    if not paragraphs:
        _log.warning("preprocess_book: no paragraphs found for book_id=%d", book_id)
        return []

    # ── 3. Glossary — get-or-create once per book ─────────────────────────
    glossary_svc = GlossaryService(session)
    glossary = await glossary_svc.get_or_create_for_book(book_id)

    # ── 4. RAG — batch embed all paragraphs, then query per paragraph ──────
    source_texts = [p.source_text for p in paragraphs]
    rag_embeddings: list[list[float]] | None = None
    series_store: SeriesStore | None = None

    if book.series_id is not None:
        db_path = RAG_DIR / f"series_{book.series_id}.db"
        if db_path.exists():
            try:
                rag_embeddings = embed_texts(source_texts)
                series_store = SeriesStore(db_path)
            except Exception:  # noqa: BLE001
                _log.warning(
                    "preprocess_book: failed to initialise RAG for series_id=%d; "
                    "continuing without RAG context",
                    book.series_id,
                )
                rag_embeddings = None
                series_store = None

    # ── 5. Lexicon service (MeCab + JMdict) ───────────────────────────────
    lexicon_svc = LexiconService()

    # ── 6. Build segments ─────────────────────────────────────────────────
    segments: list[PreprocessedSegment] = []
    try:
        for idx, para in enumerate(paragraphs):
            source_jp = para.source_text

            # MeCab tokens
            try:
                lex_result = lexicon_svc.translate(source_jp)
                mecab_tokens = lex_result.tokens
            except Exception:  # noqa: BLE001
                _log.warning(
                    "preprocess_book: lexicon failed for paragraph_id=%d; using []",
                    para.id,
                )
                mecab_tokens = []

            # Glossary context
            try:
                glossary_context = await glossary_svc.format_for_prompt(
                    glossary.id, source_jp
                )
            except Exception:  # noqa: BLE001
                _log.warning(
                    "preprocess_book: glossary failed for paragraph_id=%d; using ''",
                    para.id,
                )
                glossary_context = ""

            # RAG context
            rag_context = ""
            if series_store is not None and rag_embeddings is not None:
                try:
                    chunks = series_store.query(
                        query_embedding=rag_embeddings[idx],
                        top_k=rag_top_k,
                    )
                    rag_context = format_rag_context(chunks)
                except Exception:  # noqa: BLE001
                    _log.warning(
                        "preprocess_book: RAG query failed for paragraph_id=%d; using ''",
                        para.id,
                    )

            segments.append(PreprocessedSegment(
                paragraph_id=para.id,
                source_jp=source_jp,
                mecab_tokens=mecab_tokens,
                glossary_context=glossary_context,
                rag_context=rag_context,
            ))
    finally:
        if series_store is not None:
            series_store.close()

    _log.info(
        "preprocess_book: book_id=%d → %d segments (series_id=%s)",
        book_id, len(segments), book.series_id,
    )
    return segments
