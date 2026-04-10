"""
Chunks reviewed paragraphs into source/translation pairs for RAG indexing.

Paragraph-level granularity for v1.2.1. Sub-paragraph (sentence-level) is left
for a future iteration.
"""
from __future__ import annotations

from pydantic import BaseModel


class ChunkPair(BaseModel):
    book_id: int
    chapter_id: int
    paragraph_id: int
    source_text: str
    translated_text: str
    chunk_index: int


def chunk_paragraph_pairs(pairs: list[dict]) -> list[ChunkPair]:
    """
    Convert raw paragraph dicts into ChunkPair objects.

    Skips paragraphs that are missing either source or translation.
    """
    out: list[ChunkPair] = []
    idx = 0
    for p in pairs:
        src = (p.get("source_text") or "").strip()
        tgt = (p.get("translated_text") or "").strip()
        if not src or not tgt:
            continue
        out.append(ChunkPair(
            book_id=p["book_id"],
            chapter_id=p["chapter_id"],
            paragraph_id=p["paragraph_id"],
            source_text=src,
            translated_text=tgt,
            chunk_index=idx,
        ))
        idx += 1
    return out
