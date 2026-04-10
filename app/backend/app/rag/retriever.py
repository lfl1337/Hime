"""Retrieval API: query a series store with a JP source text."""
from __future__ import annotations

import logging

from ..core.paths import RAG_DIR
from .embeddings import embed_texts
from .store import SeriesStore

_log = logging.getLogger(__name__)


async def retrieve_top_k(
    series_id: int,
    query_text: str,
    top_k: int = 5,
) -> list[dict]:
    """Return top_k similar chunks from the given series, or [] if no store exists."""
    db_path = RAG_DIR / f"series_{series_id}.db"
    if not db_path.exists():
        return []
    embeddings = embed_texts([query_text])
    store = SeriesStore(db_path)
    try:
        return store.query(query_embedding=embeddings[0], top_k=top_k)
    finally:
        store.close()


def format_rag_context(chunks: list[dict]) -> str:
    """Render retrieved chunks into a prompt-friendly block."""
    if not chunks:
        return ""
    lines = ["Previous translations from this series:"]
    for c in chunks:
        lines.append(f"- <jp>{c['source_text']}</jp> → <en>{c['translated_text']}</en>")
    return "\n".join(lines)
