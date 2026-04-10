"""
Pipeline v2 — Pre-Processing endpoint.

POST /api/v1/pipeline/{book_id}/preprocess
  Triggers WS-A pre-processing for the given book.
  Returns segment count and a sample of the first 3 segments for inspection.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..pipeline.preprocessor import preprocess_book

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class SegmentSample(BaseModel):
    paragraph_id: int
    source_jp: str
    mecab_token_count: int
    glossary_context: str
    rag_context: str


class PreprocessResponse(BaseModel):
    book_id: int
    segment_count: int
    sample: list[SegmentSample]


@router.post("/{book_id}/preprocess", response_model=PreprocessResponse)
async def trigger_preprocess(
    book_id: int,
    session: AsyncSession = Depends(get_session),
) -> PreprocessResponse:
    """
    Pre-process all paragraphs for *book_id*.

    - Loads paragraphs from SQLite (ordered by chapter + paragraph index).
    - MeCab-tokenizes each paragraph.
    - Injects glossary context for known terms.
    - Injects RAG context from the series vector store (if available).

    Returns segment count and a sample of up to 3 segments for inspection.
    """
    try:
        segments = await preprocess_book(book_id=book_id, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    sample = [
        SegmentSample(
            paragraph_id=seg.paragraph_id,
            source_jp=seg.source_jp,
            mecab_token_count=len(seg.mecab_tokens),
            glossary_context=seg.glossary_context,
            rag_context=seg.rag_context,
        )
        for seg in segments[:3]
    ]

    return PreprocessResponse(
        book_id=book_id,
        segment_count=len(segments),
        sample=sample,
    )
