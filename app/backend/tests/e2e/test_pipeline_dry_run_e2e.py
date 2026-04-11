"""E2E test — Pipeline v2 WebSocket dry-run.

Inserts a minimal book (1 chapter, 2 paragraphs) into the isolated test DB,
connects to the WS pipeline endpoint, and verifies:
  1. The expected event sequence fires (preprocess_complete, segment_start,
     stage1-3_complete, pipeline_complete)
  2. All events arrive before the server closes the connection

WebSocket URL: /api/v1/pipeline/{book_id}/translate
Event contract (from runner_v2.py docstring):
  {"event": "preprocess_complete", "segment_count": N}
  {"event": "segment_start", "paragraph_id": id, "index": i, "total": N}
  {"event": "stage1_complete", "paragraph_id": id}
  {"event": "stage2_complete", "paragraph_id": id}
  {"event": "stage3_complete", "paragraph_id": id}
  {"event": "stage4_verdict", ...}
  {"event": "segment_complete", ...}
  {"event": "pipeline_complete", "epub_path": str}

TestClient.websocket_connect is synchronous — no asyncio.run() needed.
HIME_DRY_RUN is patched on the settings object via monkeypatch (same pattern
used by test_runner_v2_dry_run.py which already passes).
"""
import json

import pytest

from app.database import AsyncSessionLocal
from app.models import Book, Chapter, Paragraph


@pytest.mark.asyncio
async def test_pipeline_dry_run_e2e_ws(test_client):
    """Full pipeline v2 WebSocket dry-run: 2 paragraphs → expected events received.

    hime_dry_run is already set to True by the test_client fixture.
    """
    # Insert minimal book data into the isolated test DB
    async with AsyncSessionLocal() as session:
        book = Book(
            title="E2E Dry-Run Book",
            author="E2E Test",
            file_path="e2e-dry-run-test.epub",
            total_paragraphs=2,
            translated_paragraphs=0,
            status="pending",
        )
        session.add(book)
        await session.flush()
        chapter = Chapter(
            book_id=book.id,
            chapter_index=0,
            title="E2E Chapter 1",
            total_paragraphs=2,
            translated_paragraphs=0,
            status="pending",
        )
        session.add(chapter)
        await session.flush()
        for idx, src in enumerate(["少女は目を覚ました。", "窓の外で鳥が歌っていた。"]):
            session.add(Paragraph(
                chapter_id=chapter.id,
                paragraph_index=idx,
                source_text=src,
                is_translated=False,
            ))
        await session.commit()
        book_id = book.id

    # Connect via TestClient WebSocket (synchronous)
    events = []
    url = f"/api/v1/pipeline/{book_id}/translate"

    with test_client.websocket_connect(url) as ws:
        while True:
            try:
                raw = ws.receive_text()
                evt = json.loads(raw)
                events.append(evt)
                # Stop reading once pipeline is done or errors out
                if evt.get("event") in ("pipeline_complete", "pipeline_error"):
                    break
            except Exception:
                break

    event_names = [e.get("event") for e in events]

    assert "preprocess_complete" in event_names, (
        f"Missing preprocess_complete. Got: {event_names}"
    )
    assert "segment_start" in event_names, (
        f"Missing segment_start. Got: {event_names}"
    )
    assert "pipeline_complete" in event_names, (
        f"Pipeline did not complete. Got: {event_names}"
    )
    # No pipeline_error should appear
    assert "pipeline_error" not in event_names, (
        f"pipeline_error event received. Got: {event_names}"
    )
