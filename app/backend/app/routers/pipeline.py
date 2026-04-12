"""
Pipeline v2 endpoints.

POST /api/v1/pipeline/{book_id}/preprocess
  Triggers WS-A pre-processing for the given book.

WS   /ws/pipeline/{book_id}/translate
  Full book-level v2 translation via run_pipeline_v2.
  Emits structured JSON events; closes with None sentinel.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..middleware.rate_limit import limiter
from ..pipeline.preprocessor import preprocess_book
from ..pipeline.runner_v2 import run_pipeline_v2

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
@limiter.limit("5/minute")
async def trigger_preprocess(
    request: Request,
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


# ---------------------------------------------------------------------------
# WebSocket — full book translation (Pipeline v2)
# ---------------------------------------------------------------------------

# Tracks in-flight v2 jobs keyed by book_id to prevent double-spawning
_active_v2: dict[int, asyncio.Task] = {}


@router.websocket("/{book_id}/translate")
async def ws_translate_book(
    book_id: int,
    websocket: WebSocket,
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Stream a full-book Pipeline v2 translation.

    Connect:  ws://127.0.0.1:18420/api/v1/pipeline/{book_id}/translate
    Events:   JSON objects per runner_v2 contract (see runner_v2.py docstring)
    Closes:   server sends close after pipeline_complete or pipeline_error
    """
    await websocket.accept()

    if book_id in _active_v2 and not _active_v2[book_id].done():
        await websocket.send_json({
            "event": "pipeline_error",
            "detail": f"Book {book_id} is already being translated.",
        })
        await websocket.close()
        return

    ws_queue: asyncio.Queue = asyncio.Queue()

    task = asyncio.create_task(run_pipeline_v2(book_id, ws_queue, session))
    _active_v2[book_id] = task

    try:
        while True:
            try:
                event = await asyncio.wait_for(ws_queue.get(), timeout=300.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"event": "pipeline_error", "detail": "Timeout waiting for pipeline event."})
                task.cancel()
                break

            if event is None:
                # Sentinel — pipeline finished
                break

            try:
                await websocket.send_json(event)
            except WebSocketDisconnect:
                _log.info("[pipeline-ws] Client disconnected for book %d — pipeline task continues.", book_id)
                break

    except WebSocketDisconnect:
        _log.info("[pipeline-ws] WebSocket disconnect for book %d.", book_id)
    finally:
        _active_v2.pop(book_id, None)
        try:
            await websocket.close()
        except Exception:
            pass
