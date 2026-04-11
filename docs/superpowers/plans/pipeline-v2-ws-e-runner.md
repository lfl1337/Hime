# Pipeline v2 — WS-E: Runner Orchestrator v2 + EPUB Export

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire all pipeline v2 stages (preprocessor, stage1, stage2_merger, stage3_polish, stage4 reader+aggregator with retry loop) into a new `runner_v2.py` orchestrator, add a `postprocessor.py` for segment reassembly, and build `epub_export_service.py` that rebuilds a translated EPUB from the database.

**Architecture:** `runner_v2.py` replaces `runner.py` for new book-level translation jobs. The old `runner.py` stays for backward compat (single-paragraph jobs). `postprocessor.py` handles chapter reassembly from completed paragraph translations. `epub_export_service.py` uses `ebooklib` to write the final translated EPUB. All stage modules (preprocessor, stage1, stage2_merger, stage3_polish, stage4_reader, stage4_aggregator) are imported — implementations live in WS-A through WS-D.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy async, `ebooklib>=0.20` (already in `pyproject.toml`)

**Dependencies:**
- **WS-A** (preprocessor.py) — must be done first
- **WS-B** (stage1 local inference adapters) — must be done first
- **WS-C** (stage2_merger.py, stage3_polish.py) — must be done first
- **WS-D** (stage4_reader.py, stage4_aggregator.py) — must be done first
- WS-E can be planned and tested (with mocks) in parallel with WS-A through WS-D, but cannot run end-to-end until all four are complete.

---

## Constraints (READ FIRST)

1. **DO NOT modify `runner.py`** — the old pipeline remains functional for single-paragraph endpoints. Only add new files.
2. **ebooklib is already in `pyproject.toml`** — do not add it again. Verify presence before modifying.
3. **All DB writes use the passed `AsyncSession`** for checkpoints within a job. Short-lived `AsyncSessionLocal()` contexts are used only for fire-and-forget checkpoints that need to survive WS disconnects (same pattern as `runner.py:_checkpoint()`).
4. **EPUB export path** uses `DATA_DIR / "exports"` from `app.core.paths` — never hardcoded.
5. **No external API calls** — all stage inference goes to local `127.0.0.1` endpoints.
6. **Stage modules assumed interface** (confirmed by WS-A through WS-D plans):
   - `preprocessor.preprocess_book(book_id, session)` → `list[PreprocessedSegment]`
   - `stage1.run_stage1(segment, session)` → `Stage1Drafts`
   - `stage2_merger.merge(drafts, session)` → `str`
   - `stage3_polish.polish(merged_str, session)` → `str`
   - `stage4_reader.review(polished_str, session)` → `list[ReaderAnnotation]`
   - `stage4_aggregator.aggregate(annotations)` → `AggregatorVerdict` with `.verdict: str` and `.retry_instruction: str | None` and `.confidence: dict`

---

## File Map

### New files
| Path | Responsibility |
|------|---------------|
| `app/backend/app/pipeline/runner_v2.py` | Book-level pipeline orchestrator — wires all stages |
| `app/backend/app/pipeline/postprocessor.py` | Segment reassembly + chapter text builder |
| `app/backend/app/services/epub_export_service.py` | Build translated EPUB from DB using ebooklib |
| `app/backend/tests/test_runner_v2.py` | Tests: events, retry loop, retry cap, DB checkpoint, EPUB export |

### Modified files
| Path | What changes |
|------|--------------|
| `app/backend/pyproject.toml` | Verify `ebooklib>=0.20` present (no-op if already there — document finding) |
| `app/backend/app/pipeline/__init__.py` | Export `run_pipeline_v2` for import by routers |

---

## Task 1: `postprocessor.py` — Segment Reassembly

**Files:**
- Create: `app/backend/app/pipeline/postprocessor.py`

### Step 1.1 — Implement `reassemble_chapter` and `postprocess_book`

- [ ] Create `app/backend/app/pipeline/postprocessor.py` with full implementation:

```python
"""
postprocessor.py — Reassemble translated paragraph segments into chapter text.

Used by runner_v2 after all segments are checkpointed, and by epub_export_service
to build per-chapter text blocks for EPUB chapter items.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Book, Chapter, Paragraph


def reassemble_chapter(paragraphs: list[tuple[int, str]], chapter_title: str) -> str:
    """
    Join translated paragraphs back into chapter text with title.

    Args:
        paragraphs: List of (paragraph_index, translated_text) tuples, ordered by index.
        chapter_title: Title string to prepend as an H1-style header.

    Returns:
        Full chapter text with title line, blank line, then paragraphs separated
        by double newlines.
    """
    lines: list[str] = [chapter_title, ""]
    for _idx, text in paragraphs:
        lines.append(text.strip())
    return "\n\n".join(lines)


async def postprocess_book(book_id: int, session: AsyncSession) -> dict[int, str]:
    """
    Return {chapter_id: full_translated_text} for all chapters of a book.

    Fetches all chapters ordered by chapter_index, then for each chapter
    fetches all paragraphs ordered by paragraph_index.  Uses translated_text
    if available, falls back to source_text wrapped in [untranslated: ...].

    Args:
        book_id: Primary key of the Book row.
        session: Active async SQLAlchemy session.

    Returns:
        Dict mapping chapter_id → assembled translated chapter text.
    """
    result = await session.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.chapter_index)
    )
    chapters = result.scalars().all()

    chapter_texts: dict[int, str] = {}
    for chapter in chapters:
        para_result = await session.execute(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
        paragraphs = para_result.scalars().all()

        para_tuples: list[tuple[int, str]] = []
        for p in paragraphs:
            if p.translated_text:
                para_tuples.append((p.paragraph_index, p.translated_text))
            else:
                fallback = f"[untranslated: {p.source_text[:80]}]"
                para_tuples.append((p.paragraph_index, fallback))

        chapter_texts[chapter.id] = reassemble_chapter(para_tuples, chapter.title)

    return chapter_texts
```

---

## Task 2: `epub_export_service.py` — EPUB Builder

**Files:**
- Create: `app/backend/app/services/epub_export_service.py`

### Step 2.1 — Implement `export_book`

- [ ] Create `app/backend/app/services/epub_export_service.py` with full implementation:

```python
"""
epub_export_service.py — Build a translated EPUB from translated paragraphs in DB.

Reads Book metadata, all Chapters and their translated Paragraphs, assembles
chapter HTML documents, and writes an ebooklib EpubBook to the exports directory.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.paths import DATA_DIR
from ..models import Book, Chapter, Paragraph
from ..pipeline.postprocessor import postprocess_book

_log = logging.getLogger(__name__)

EXPORTS_DIR = DATA_DIR / "exports"


def _build_epub_sync(
    book_title: str,
    book_author: str | None,
    cover_blob: bytes | None,
    chapter_data: list[dict],  # [{"title": str, "text": str}]
    output_path: Path,
) -> None:
    """Synchronous ebooklib EPUB construction — run inside asyncio.to_thread."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(f"hime-export-{output_path.stem}")
    book.set_title(book_title)
    book.set_language("en")
    if book_author:
        book.add_author(book_author)

    # Cover image
    if cover_blob:
        cover_item = epub.EpubItem(
            uid="cover-image",
            file_name="images/cover.jpg",
            media_type="image/jpeg",
            content=cover_blob,
        )
        book.add_item(cover_item)
        book.set_cover("images/cover.jpg", cover_blob)

    chapters: list[epub.EpubHtml] = []
    toc: list[epub.Link] = []
    spine: list[str | epub.EpubHtml] = ["nav"]

    for idx, ch in enumerate(chapter_data):
        ch_id = f"chapter_{idx:04d}"
        ch_filename = f"{ch_id}.xhtml"
        title_safe = ch["title"].replace('"', "&quot;").replace("<", "&lt;")
        # Convert plain text paragraphs to HTML <p> elements
        paragraphs_html = "".join(
            f"<p>{para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</p>"
            for para in ch["text"].split("\n\n")
            if para.strip() and para.strip() != ch["title"]
        )
        html_content = (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<!DOCTYPE html>'
            f'<html xmlns="http://www.w3.org/1999/xhtml">'
            f'<head><title>{title_safe}</title>'
            f'<link rel="stylesheet" type="text/css" href="../styles/main.css"/>'
            f"</head><body>"
            f"<h1>{title_safe}</h1>"
            f"{paragraphs_html}"
            f"</body></html>"
        )

        ch_item = epub.EpubHtml(
            uid=ch_id,
            file_name=f"Text/{ch_filename}",
            title=ch["title"],
            lang="en",
        )
        ch_item.set_content(html_content.encode("utf-8"))
        book.add_item(ch_item)
        chapters.append(ch_item)
        toc.append(epub.Link(f"Text/{ch_filename}", ch["title"], ch_id))
        spine.append(ch_item)

    # Basic CSS
    css_item = epub.EpubItem(
        uid="style-main",
        file_name="styles/main.css",
        media_type="text/css",
        content=b"body { font-family: serif; line-height: 1.6; margin: 1em 2em; }"
                b" h1 { margin-bottom: 1em; } p { margin: 0.5em 0; text-indent: 1.5em; }",
    )
    book.add_item(css_item)

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book)
    _log.info("[epub-export] Written: %s", output_path)


async def export_book(book_id: int, session: AsyncSession) -> Path:
    """
    Build an EPUB from translated paragraphs in DB. Returns the output path.

    Steps:
    1. Load Book metadata (title, author, cover_image_blob).
    2. Load all Chapters ordered by chapter_index.
    3. Call postprocess_book() to get {chapter_id: full_text} mapping.
    4. Build ordered list of {title, text} chapter dicts.
    5. Construct EPUB via ebooklib in a thread (blocking I/O).
    6. Write to DATA_DIR/exports/{book_id}_translated.epub.

    Args:
        book_id: Primary key of the Book to export.
        session: Active async SQLAlchemy session.

    Returns:
        Path to the written EPUB file.

    Raises:
        ValueError: If the Book is not found.
    """
    book = await session.get(Book, book_id)
    if book is None:
        raise ValueError(f"Book {book_id} not found")

    result = await session.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.chapter_index)
    )
    chapters = result.scalars().all()

    # Get {chapter_id: full_text}
    chapter_texts = await postprocess_book(book_id, session)

    chapter_data: list[dict] = [
        {"title": ch.title, "text": chapter_texts.get(ch.id, "")}
        for ch in chapters
    ]

    output_path = EXPORTS_DIR / f"{book_id}_translated.epub"

    await asyncio.to_thread(
        _build_epub_sync,
        book.title,
        book.author,
        book.cover_image_blob,
        chapter_data,
        output_path,
    )

    return output_path
```

### Step 2.2 — Verify `ebooklib` in `pyproject.toml`

- [ ] Open `app/backend/pyproject.toml`, confirm `ebooklib>=0.20` is already listed under `dependencies`. If present: no change needed. If missing (unlikely): add `"ebooklib>=0.20"` to the `dependencies` list. Document the finding in a comment at the top of `epub_export_service.py`.

---

## Task 3: `runner_v2.py` — Pipeline Orchestrator

**Files:**
- Create: `app/backend/app/pipeline/runner_v2.py`

### Step 3.1 — Implement the full orchestrator

- [ ] Create `app/backend/app/pipeline/runner_v2.py`:

```python
"""
runner_v2.py — Book-level pipeline v2 orchestrator.

Wires together:
  preprocessor → stage1 → stage2_merger → stage3_polish → stage4 (retry loop)
  → DB checkpoint per segment → epub_export on completion

The old runner.py stays for backward compat (single-paragraph /translate jobs).
This runner handles full-book translation jobs triggered by the /books/{id}/translate
endpoint (to be wired by WS-E integration step).

WebSocket event contract (emitted to ws_queue):
  {"event": "preprocess_complete", "segment_count": N}
  {"event": "segment_start", "paragraph_id": id, "index": i, "total": N}
  {"event": "stage1_complete", "paragraph_id": id}
  {"event": "stage2_complete", "paragraph_id": id}
  {"event": "stage3_complete", "paragraph_id": id}
  {"event": "stage4_verdict", "paragraph_id": id, "verdict": "okay"|"retry", "retry_count": n}
  {"event": "segment_complete", "paragraph_id": id, "translation": text}
  {"event": "pipeline_complete", "epub_path": str}
  {"event": "pipeline_error", "detail": str}
  None  ← sentinel: tells drain loop the pipeline is done

DB checkpoint per segment: upsert Translation row for the paragraph with
  final_output, current_stage="complete", confidence_log (JSON string).
Also updates Paragraph.translated_text, Paragraph.is_translated, Paragraph.translated_at.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models import Chapter, Paragraph, Translation
from ..services.epub_export_service import export_book

# Stage module imports — implementations provided by WS-A through WS-D.
# These are imported at function scope to allow mocking in tests.

_log = logging.getLogger(__name__)

MAX_STAGE4_RETRIES = 3


async def _checkpoint_segment(
    paragraph_id: int,
    final_text: str,
    confidence_log: dict | None,
) -> None:
    """
    Persist a completed segment translation.

    Uses its own short-lived AsyncSessionLocal session so the checkpoint
    survives a WebSocket disconnect (same pattern as old runner.py:_checkpoint).

    Updates:
    - Paragraph.translated_text, .is_translated, .translated_at
    - Translation upsert (find by paragraph source_text_id or create new)
      with final_output, current_stage="complete", confidence_log
    """
    async with AsyncSessionLocal() as session:
        paragraph = await session.get(Paragraph, paragraph_id)
        if paragraph is None:
            _log.warning("[runner_v2] Paragraph %d not found for checkpoint", paragraph_id)
            return

        paragraph.translated_text = final_text
        paragraph.is_translated = True
        paragraph.translated_at = datetime.now(UTC)

        # Update chapter + book progress counters
        chapter = await session.get(Chapter, paragraph.chapter_id)
        if chapter:
            from sqlalchemy import select as _select
            res = await session.execute(
                _select(Paragraph).where(
                    Paragraph.chapter_id == chapter.id,
                    Paragraph.is_translated == True,  # noqa: E712
                )
            )
            chapter.translated_paragraphs = len(res.scalars().all()) + 1  # +1 for current
            chapter.status = (
                "complete"
                if chapter.translated_paragraphs >= chapter.total_paragraphs
                else "in_progress"
            )

            from ..models import Book
            book = await session.get(Book, chapter.book_id)
            if book:
                from sqlalchemy import select as _sel
                res2 = await session.execute(
                    _sel(Paragraph)
                    .join(Chapter, Paragraph.chapter_id == Chapter.id)
                    .where(Chapter.book_id == book.id, Paragraph.is_translated == True)  # noqa: E712
                )
                book.translated_paragraphs = len(res2.scalars().all()) + 1
                book.status = (
                    "complete"
                    if book.translated_paragraphs >= book.total_paragraphs
                    else "in_progress"
                )

        # Upsert Translation row (linked via source_text_id — not used in v2 book flow,
        # so we store a standalone Translation keyed by paragraph content hash or just
        # look for an existing one with matching paragraph source_text_id).
        # For v2, Paragraph does not have a source_text FK, so we store a free-standing
        # Translation row using paragraph.id as a surrogate via a convention:
        # model="pipeline_v2", notes=f"paragraph:{paragraph_id}"
        res_tr = await session.execute(
            select(Translation).where(
                Translation.notes == f"paragraph:{paragraph_id}",
                Translation.model == "pipeline_v2",
            )
        )
        translation = res_tr.scalar_one_or_none()
        if translation is None:
            # We need a source_text_id — use paragraph's chapter's first SourceText
            # if available, else skip Translation row creation and rely on Paragraph row alone.
            # In v2, the canonical output is Paragraph.translated_text; Translation is
            # supplementary for confidence logging.
            try:
                from ..models import SourceText
                st = SourceText(
                    title=f"para:{paragraph_id}",
                    content=paragraph.source_text,
                    language="ja",
                )
                session.add(st)
                await session.flush()
                translation = Translation(
                    source_text_id=st.id,
                    content=final_text,
                    model="pipeline_v2",
                    notes=f"paragraph:{paragraph_id}",
                )
                session.add(translation)
                await session.flush()
            except Exception as exc:  # noqa: BLE001
                _log.warning("[runner_v2] Could not create Translation row: %s", exc)
                translation = None

        if translation is not None:
            translation.content = final_text
            translation.final_output = final_text
            translation.current_stage = "complete"
            if confidence_log is not None:
                translation.confidence_log = json.dumps(confidence_log)

        await session.commit()


async def run_pipeline_v2(
    book_id: int,
    ws_queue: asyncio.Queue,
    session: AsyncSession,
) -> None:
    """
    Full book-level pipeline v2 coroutine.

    Designed to run as an asyncio.Task so that a WebSocket disconnect does not
    abort in-flight inference calls. Emits structured events to ws_queue.
    Emits a None sentinel at the end (success or error) to signal the drain loop.

    Args:
        book_id: Primary key of the Book to translate.
        ws_queue: asyncio.Queue for WebSocket event dicts.
        session: AsyncSession for initial DB reads (preprocessor uses this).
                 Per-segment checkpoints open their own AsyncSessionLocal sessions.
    """
    # Lazy imports of stage modules — allows test mocking via unittest.mock.patch
    from . import preprocessor as _preprocessor
    from . import stage1 as _stage1
    from . import stage2_merger as _stage2
    from . import stage3_polish as _stage3
    from . import stage4_aggregator as _stage4_agg
    from . import stage4_reader as _stage4_reader

    try:
        # ------------------------------------------------------------------ #
        # Pre-process: EPUB paragraphs → list[PreprocessedSegment]            #
        # ------------------------------------------------------------------ #
        segments = await _preprocessor.preprocess_book(book_id, session)
        total = len(segments)
        await ws_queue.put({"event": "preprocess_complete", "segment_count": total})

        for i, segment in enumerate(segments):
            paragraph_id: int = segment.paragraph_id
            await ws_queue.put({
                "event": "segment_start",
                "paragraph_id": paragraph_id,
                "index": i,
                "total": total,
            })

            # ------------------------------------------------------------------ #
            # Stage 1 — local inference adapters → Stage1Drafts                  #
            # ------------------------------------------------------------------ #
            drafts = await _stage1.run_stage1(segment, session)
            await ws_queue.put({"event": "stage1_complete", "paragraph_id": paragraph_id})

            # ------------------------------------------------------------------ #
            # Stage 2 — merger → merged_str                                       #
            # ------------------------------------------------------------------ #
            merged_str = await _stage2.merge(drafts, session)
            await ws_queue.put({"event": "stage2_complete", "paragraph_id": paragraph_id})

            # ------------------------------------------------------------------ #
            # Stage 3 — polish → polished_str                                     #
            # ------------------------------------------------------------------ #
            polished_str = await _stage3.polish(merged_str, session)
            await ws_queue.put({"event": "stage3_complete", "paragraph_id": paragraph_id})

            # ------------------------------------------------------------------ #
            # Stage 4 — Reader Panel × aggregator with retry loop (max 3)         #
            # ------------------------------------------------------------------ #
            retry_count = 0
            current_polished = polished_str
            confidence_log: dict | None = None

            while True:
                annotations = await _stage4_reader.review(current_polished, session)
                verdict_obj = await _stage4_agg.aggregate(annotations)
                confidence_log = getattr(verdict_obj, "confidence", None)

                await ws_queue.put({
                    "event": "stage4_verdict",
                    "paragraph_id": paragraph_id,
                    "verdict": verdict_obj.verdict,
                    "retry_count": retry_count,
                })

                if verdict_obj.verdict == "retry" and retry_count < MAX_STAGE4_RETRIES:
                    retry_count += 1
                    # Re-polish with retry instruction from aggregator
                    retry_instruction = getattr(verdict_obj, "retry_instruction", "") or ""
                    current_polished = await _stage3.polish(
                        merged_str, session, retry_instruction=retry_instruction
                    )
                else:
                    # Accept: either "okay", or retry cap reached
                    break

            final_text = current_polished

            # ------------------------------------------------------------------ #
            # DB checkpoint — persists translation, updates Paragraph row          #
            # ------------------------------------------------------------------ #
            await _checkpoint_segment(paragraph_id, final_text, confidence_log)

            await ws_queue.put({
                "event": "segment_complete",
                "paragraph_id": paragraph_id,
                "translation": final_text,
            })

        # ------------------------------------------------------------------ #
        # Post-process: build EPUB from all translated paragraphs             #
        # ------------------------------------------------------------------ #
        epub_path = await export_book(book_id, session)
        await ws_queue.put({
            "event": "pipeline_complete",
            "epub_path": str(epub_path),
        })

    except Exception as exc:
        _log.exception("[runner_v2] Pipeline error for book %d", book_id)
        await ws_queue.put({"event": "pipeline_error", "detail": str(exc)})

    finally:
        # Sentinel: tells the drain loop that the pipeline is done
        await ws_queue.put(None)
```

### Step 3.2 — Update `pipeline/__init__.py`

- [ ] Open `app/backend/app/pipeline/__init__.py`. Add the following import so routers can do `from app.pipeline import run_pipeline_v2`:

```python
from .runner_v2 import run_pipeline_v2  # noqa: F401
```

If the file is empty or only has a docstring, add it after any existing content.

---

## Task 4: Write Tests

**Files:**
- Create: `app/backend/tests/test_runner_v2.py`

### Step 4.1 — Write the full test file (TDD: write tests before running implementation)

- [ ] Create `app/backend/tests/test_runner_v2.py`:

```python
"""
Tests for pipeline v2 runner orchestrator and EPUB export service.

All stage modules are mocked — no actual model inference is required.
DB operations use an in-memory SQLite async engine.

Test inventory:
  test_preprocess_complete_event        — runner emits preprocess_complete with segment_count
  test_retry_loop_repoliched_twice      — aggregator returns retry×2 then okay; polish called 3× total
  test_retry_cap_accepts_after_3        — aggregator always returns retry; stops at 3 and accepts
  test_db_checkpoint_written            — Paragraph.translated_text is set after segment_complete
  test_export_book_creates_file         — export_book writes a file at expected path (mocked ebooklib)
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

# ---------------------------------------------------------------------------
# In-memory DB setup
# ---------------------------------------------------------------------------

from app.database import Base
from app.models import Book, Chapter, Paragraph


@pytest_asyncio.fixture
async def async_session():
    """Provide a fresh in-memory SQLite async session for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_book(async_session):
    """Insert a minimal Book → Chapter → Paragraph hierarchy and return IDs."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_segment(paragraph_id: int, text: str = "彼女は微笑んだ。"):
    """Build a minimal PreprocessedSegment-like namespace."""
    return SimpleNamespace(paragraph_id=paragraph_id, source_text=text)


def _make_verdict(verdict: str, retry_instruction: str = "Fix tone.", confidence: dict | None = None):
    """Build a minimal AggregatorVerdict-like namespace."""
    return SimpleNamespace(
        verdict=verdict,
        retry_instruction=retry_instruction,
        confidence=confidence or {"score": 0.8},
    )


async def _drain_queue(q: asyncio.Queue) -> list[dict]:
    """Drain all events from a queue until the None sentinel."""
    events = []
    while True:
        item = await asyncio.wait_for(q.get(), timeout=2.0)
        if item is None:
            break
        events.append(item)
    return events


# ---------------------------------------------------------------------------
# Test: preprocess_complete event emitted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preprocess_complete_event(seeded_book, async_session):
    """run_pipeline_v2 must emit preprocess_complete with the correct segment_count."""
    paragraph_id = seeded_book["paragraph_id"]

    fake_segment = _make_segment(paragraph_id)
    fake_verdict = _make_verdict("okay")

    with (
        patch("app.pipeline.runner_v2.preprocessor") as mock_pre,
        patch("app.pipeline.runner_v2.stage1") as mock_s1,
        patch("app.pipeline.runner_v2.stage2_merger") as mock_s2,
        patch("app.pipeline.runner_v2.stage3_polish") as mock_s3,
        patch("app.pipeline.runner_v2.stage4_reader") as mock_s4r,
        patch("app.pipeline.runner_v2.stage4_aggregator") as mock_s4a,
        patch("app.pipeline.runner_v2.export_book", new_callable=AsyncMock) as mock_export,
        patch("app.pipeline.runner_v2._checkpoint_segment", new_callable=AsyncMock),
    ):
        mock_pre.preprocess_book = AsyncMock(return_value=[fake_segment])
        mock_s1.run_stage1 = AsyncMock(return_value=MagicMock())
        mock_s2.merge = AsyncMock(return_value="merged text")
        mock_s3.polish = AsyncMock(return_value="polished text")
        mock_s4r.review = AsyncMock(return_value=[MagicMock()])
        mock_s4a.aggregate = AsyncMock(return_value=fake_verdict)
        mock_export.return_value = Path("/fake/exports/1_translated.epub")

        from app.pipeline.runner_v2 import run_pipeline_v2

        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(seeded_book["book_id"], q, async_session)

        events = await _drain_queue(q)

    event_types = [e["event"] for e in events]
    assert "preprocess_complete" in event_types

    pre_event = next(e for e in events if e["event"] == "preprocess_complete")
    assert pre_event["segment_count"] == 1


# ---------------------------------------------------------------------------
# Test: retry loop re-polishes exactly N times
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_loop_repolished_twice(seeded_book, async_session):
    """
    If aggregator returns retry twice then okay, stage3_polish must be called 3× total:
    once for initial polish, once per retry.
    """
    paragraph_id = seeded_book["paragraph_id"]
    fake_segment = _make_segment(paragraph_id)

    # Verdicts: retry, retry, okay
    verdicts = [
        _make_verdict("retry", "Fix tone."),
        _make_verdict("retry", "Fix register."),
        _make_verdict("okay"),
    ]
    verdict_iter = iter(verdicts)

    with (
        patch("app.pipeline.runner_v2.preprocessor") as mock_pre,
        patch("app.pipeline.runner_v2.stage1") as mock_s1,
        patch("app.pipeline.runner_v2.stage2_merger") as mock_s2,
        patch("app.pipeline.runner_v2.stage3_polish") as mock_s3,
        patch("app.pipeline.runner_v2.stage4_reader") as mock_s4r,
        patch("app.pipeline.runner_v2.stage4_aggregator") as mock_s4a,
        patch("app.pipeline.runner_v2.export_book", new_callable=AsyncMock) as mock_export,
        patch("app.pipeline.runner_v2._checkpoint_segment", new_callable=AsyncMock),
    ):
        mock_pre.preprocess_book = AsyncMock(return_value=[fake_segment])
        mock_s1.run_stage1 = AsyncMock(return_value=MagicMock())
        mock_s2.merge = AsyncMock(return_value="merged text")
        # polish is called once initially (stage3), then once per retry → 3 total
        mock_s3.polish = AsyncMock(side_effect=["polished v1", "polished v2", "polished v3"])
        mock_s4r.review = AsyncMock(return_value=[MagicMock()])
        mock_s4a.aggregate = AsyncMock(side_effect=lambda _anns: next(verdict_iter))
        mock_export.return_value = Path("/fake/exports/1_translated.epub")

        from importlib import reload
        import app.pipeline.runner_v2 as rv2
        reload(rv2)  # ensure fresh module with patches applied

        q: asyncio.Queue = asyncio.Queue()
        await rv2.run_pipeline_v2(seeded_book["book_id"], q, async_session)
        await _drain_queue(q)

    # stage3_polish.polish called: 1 (initial) + 2 (retries) = 3
    assert mock_s3.polish.call_count == 3


# ---------------------------------------------------------------------------
# Test: retry cap — stops at MAX_STAGE4_RETRIES and accepts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_cap_accepts_after_3(seeded_book, async_session):
    """
    If aggregator always returns retry, the runner must stop after MAX_STAGE4_RETRIES (3)
    and accept the translation — not loop forever.
    """
    paragraph_id = seeded_book["paragraph_id"]
    fake_segment = _make_segment(paragraph_id)
    always_retry = _make_verdict("retry", "Still not great.")

    polish_call_count = 0

    async def counting_polish(text, session, retry_instruction=""):
        nonlocal polish_call_count
        polish_call_count += 1
        return f"polished v{polish_call_count}"

    with (
        patch("app.pipeline.runner_v2.preprocessor") as mock_pre,
        patch("app.pipeline.runner_v2.stage1") as mock_s1,
        patch("app.pipeline.runner_v2.stage2_merger") as mock_s2,
        patch("app.pipeline.runner_v2.stage3_polish") as mock_s3,
        patch("app.pipeline.runner_v2.stage4_reader") as mock_s4r,
        patch("app.pipeline.runner_v2.stage4_aggregator") as mock_s4a,
        patch("app.pipeline.runner_v2.export_book", new_callable=AsyncMock) as mock_export,
        patch("app.pipeline.runner_v2._checkpoint_segment", new_callable=AsyncMock),
    ):
        mock_pre.preprocess_book = AsyncMock(return_value=[fake_segment])
        mock_s1.run_stage1 = AsyncMock(return_value=MagicMock())
        mock_s2.merge = AsyncMock(return_value="merged text")
        mock_s3.polish = AsyncMock(side_effect=counting_polish)
        mock_s4r.review = AsyncMock(return_value=[MagicMock()])
        mock_s4a.aggregate = AsyncMock(return_value=always_retry)
        mock_export.return_value = Path("/fake/exports/1_translated.epub")

        from importlib import reload
        import app.pipeline.runner_v2 as rv2
        reload(rv2)

        q: asyncio.Queue = asyncio.Queue()
        await rv2.run_pipeline_v2(seeded_book["book_id"], q, async_session)
        events = await _drain_queue(q)

    # MAX_STAGE4_RETRIES = 3, so polish is called: 1 initial + 3 retries = 4 total
    assert polish_call_count == 4

    # pipeline_complete must still be emitted (no pipeline_error)
    event_types = [e["event"] for e in events]
    assert "pipeline_complete" in event_types
    assert "pipeline_error" not in event_types

    # All stage4_verdict events must have retry or the final cap acceptance
    verdict_events = [e for e in events if e["event"] == "stage4_verdict"]
    # 4 verdicts emitted: retry×3 then retry at cap (accepted)
    assert len(verdict_events) == 4
    # All are "retry" because aggregator always returns retry
    assert all(e["verdict"] == "retry" for e in verdict_events)


# ---------------------------------------------------------------------------
# Test: DB checkpoint written after each segment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_checkpoint_written(seeded_book, async_session):
    """
    After run_pipeline_v2 completes, _checkpoint_segment must be called once
    per segment with the correct paragraph_id and final_text.
    """
    paragraph_id = seeded_book["paragraph_id"]
    fake_segment = _make_segment(paragraph_id)
    fake_verdict = _make_verdict("okay", confidence={"score": 0.95})

    checkpoint_calls = []

    async def fake_checkpoint(pid, text, confidence):
        checkpoint_calls.append({"paragraph_id": pid, "text": text, "confidence": confidence})

    with (
        patch("app.pipeline.runner_v2.preprocessor") as mock_pre,
        patch("app.pipeline.runner_v2.stage1") as mock_s1,
        patch("app.pipeline.runner_v2.stage2_merger") as mock_s2,
        patch("app.pipeline.runner_v2.stage3_polish") as mock_s3,
        patch("app.pipeline.runner_v2.stage4_reader") as mock_s4r,
        patch("app.pipeline.runner_v2.stage4_aggregator") as mock_s4a,
        patch("app.pipeline.runner_v2.export_book", new_callable=AsyncMock) as mock_export,
        patch("app.pipeline.runner_v2._checkpoint_segment", side_effect=fake_checkpoint),
    ):
        mock_pre.preprocess_book = AsyncMock(return_value=[fake_segment])
        mock_s1.run_stage1 = AsyncMock(return_value=MagicMock())
        mock_s2.merge = AsyncMock(return_value="merged text")
        mock_s3.polish = AsyncMock(return_value="polished text")
        mock_s4r.review = AsyncMock(return_value=[MagicMock()])
        mock_s4a.aggregate = AsyncMock(return_value=fake_verdict)
        mock_export.return_value = Path("/fake/exports/1_translated.epub")

        from importlib import reload
        import app.pipeline.runner_v2 as rv2
        reload(rv2)

        q: asyncio.Queue = asyncio.Queue()
        await rv2.run_pipeline_v2(seeded_book["book_id"], q, async_session)
        await _drain_queue(q)

    assert len(checkpoint_calls) == 1
    call = checkpoint_calls[0]
    assert call["paragraph_id"] == paragraph_id
    assert call["text"] == "polished text"
    assert call["confidence"] == {"score": 0.95}


# ---------------------------------------------------------------------------
# Test: export_book creates file at expected path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_book_creates_file(async_session, tmp_path):
    """
    export_book must write an EPUB file at DATA_DIR/exports/{book_id}_translated.epub.
    ebooklib.epub.write_epub is mocked to avoid actual filesystem writes in DATA_DIR.
    """
    # Seed a book with one chapter and one translated paragraph
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
        # Simulate to_thread by calling the sync function directly via side_effect
        async def fake_to_thread(fn, *args, **kwargs):
            # Create the file to simulate write
            path = args[-1]  # last positional arg is output_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fake-epub-content")
        mock_thread.side_effect = fake_to_thread

        from app.services.epub_export_service import export_book

        result_path = await export_book(book.id, async_session)

    assert result_path == expected_path
    assert result_path.exists()
    assert result_path.read_bytes() == b"fake-epub-content"


# ---------------------------------------------------------------------------
# Test: postprocessor reassemble_chapter
# ---------------------------------------------------------------------------

def test_reassemble_chapter_format():
    """reassemble_chapter must prepend title, blank line, then paragraphs."""
    from app.pipeline.postprocessor import reassemble_chapter

    paras = [(0, "She smiled."), (1, "The room was quiet.")]
    result = reassemble_chapter(paras, "Chapter 1")

    lines = result.split("\n\n")
    assert lines[0] == "Chapter 1"
    assert lines[1] == ""
    assert "She smiled." in result
    assert "The room was quiet." in result


# ---------------------------------------------------------------------------
# Test: postprocess_book returns fallback for untranslated paragraphs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_postprocess_book_fallback(async_session):
    """postprocess_book uses [untranslated: ...] for paragraphs without translated_text."""
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
```

---

## Task 5: TDD Cycle — Run Tests, Fix Until Green

**Execution order (strict TDD):**

### Step 5.1 — Run tests against stubs first

- [ ] Run the test file. At this point, imports for stage modules (`preprocessor`, `stage1`, etc.) will fail because those modules don't exist yet (WS-A through WS-D are prerequisites). The tests mock all stage modules — they should pass even without real implementations if runner_v2 defers imports properly (see `from . import preprocessor as _preprocessor` inside the function body).

```bash
cd app/backend
uv run pytest tests/test_runner_v2.py -v 2>&1 | head -80
```

Expected: all 7 tests pass (stage modules are mocked at the module level with `patch`).

### Step 5.2 — Fix any import errors

- [ ] If `app.pipeline.runner_v2` fails to import because `preprocessor`, `stage1`, etc. don't exist as module files: create empty stub files for each missing module so Python can import the package. These stubs will be replaced by WS-A through WS-D.

  Create the following stub files only if not already created by WS-A/B/C/D:

  - `app/backend/app/pipeline/preprocessor.py` — if missing:
    ```python
    """Stub: replaced by WS-A implementation."""
    async def preprocess_book(book_id, session): ...
    ```
  - `app/backend/app/pipeline/stage1.py` — if missing (WS-B may use a package `stage1/`; adjust accordingly):
    ```python
    """Stub: replaced by WS-B implementation."""
    async def run_stage1(segment, session): ...
    ```
  - `app/backend/app/pipeline/stage2_merger.py` — if missing:
    ```python
    """Stub: replaced by WS-C implementation."""
    async def merge(drafts, session): ...
    ```
  - `app/backend/app/pipeline/stage3_polish.py` — if missing:
    ```python
    """Stub: replaced by WS-C implementation."""
    async def polish(merged_str, session, retry_instruction=""): ...
    ```
  - `app/backend/app/pipeline/stage4_reader.py` — if missing:
    ```python
    """Stub: replaced by WS-D implementation."""
    async def review(polished_str, session): ...
    ```
  - `app/backend/app/pipeline/stage4_aggregator.py` — if missing:
    ```python
    """Stub: replaced by WS-D implementation."""
    async def aggregate(annotations): ...
    ```

### Step 5.3 — Run tests until all pass

- [ ] Re-run `uv run pytest tests/test_runner_v2.py -v` after each fix until all 7 tests are green.

### Step 5.4 — Run full test suite (no regressions)

- [ ] Run `uv run pytest --tb=short 2>&1 | tail -20` to confirm no existing tests are broken.

---

## Task 6: Integration — Wire `run_pipeline_v2` into a Router Endpoint

> **Note:** Full router wiring may be covered by a separate WS-E integration task or by the frontend WS. This task ensures the function is importable and documents the expected call site.

### Step 6.1 — Verify importability

- [ ] Open a Python REPL or add a quick smoke-import test:
  ```python
  from app.pipeline.runner_v2 import run_pipeline_v2
  from app.services.epub_export_service import export_book
  from app.pipeline.postprocessor import postprocess_book, reassemble_chapter
  print("All imports OK")
  ```

### Step 6.2 — Document expected endpoint call site

The endpoint that triggers book-level translation should do approximately:

```python
# In a router (e.g., app/routers/books.py or app/routers/pipeline.py):
import asyncio
from fastapi import APIRouter, WebSocket, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_session
from ..pipeline.runner_v2 import run_pipeline_v2

router = APIRouter()

@router.websocket("/ws/books/{book_id}/translate")
async def translate_book_ws(book_id: int, websocket: WebSocket, session: AsyncSession = Depends(get_session)):
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_pipeline_v2(book_id, q, session))
    while True:
        event = await q.get()
        if event is None:
            break
        await websocket.send_json(event)
    await websocket.close()
```

This wiring is **not implemented by WS-E** — it is documented here for the frontend/router integration workstream.

---

## Task 7: Commit

- [ ] Stage and commit all new files:

```
feat(pipeline): WS-E runner_v2 orchestrator, postprocessor, epub_export_service + tests

- pipeline/runner_v2.py: full book-level v2 orchestrator (stage1→4, retry loop, DB checkpoint)
- pipeline/postprocessor.py: segment reassembly + postprocess_book()
- services/epub_export_service.py: ebooklib EPUB builder from translated paragraphs
- pipeline/__init__.py: export run_pipeline_v2
- tests/test_runner_v2.py: 7 tests covering events, retry loop, retry cap, DB checkpoint, export
- Stub modules for stage1/2/3/4_reader/4_aggregator/preprocessor (replaced by WS-A to WS-D)
```

Commit message format (Conventional Commits):
```
feat(pipeline): WS-E runner_v2 + epub_export_service + postprocessor + 7 tests
```

---

## Implementation Notes

### Why lazy module imports inside the function body?

`run_pipeline_v2` does `from . import preprocessor as _preprocessor` etc. *inside* the function, not at module top level. This is intentional: it lets `unittest.mock.patch("app.pipeline.runner_v2.preprocessor")` intercept the import cleanly in tests without needing the real WS-A/B/C/D modules to exist. Once WS-A–D are implemented, the imports will resolve to real modules automatically.

### Retry loop logic — authoritative description

```
retry_count = 0
current_polished = initial_polish_output  # from stage3 initial call

while True:
    annotations = stage4_reader.review(current_polished)
    verdict = stage4_aggregator.aggregate(annotations)
    emit stage4_verdict event

    if verdict == "retry" AND retry_count < MAX_STAGE4_RETRIES (3):
        retry_count += 1
        current_polished = stage3_polish(merged_str, retry_instruction=verdict.retry_instruction)
        # loop again
    else:
        break  # either "okay", or retry cap hit
```

Total `stage3.polish` calls: 1 (initial, before the loop) + N retry calls (up to 3). Total aggregator calls: up to 4 (initial + 3 retries). If aggregator always returns "retry", the runner accepts after the 3rd retry (4th aggregator call, 4th polish call) and moves on — no `pipeline_error`.

### Translation row strategy

The v2 pipeline translates at Paragraph granularity. The legacy `Translation` table links to `SourceText` (which was for single-text translation jobs). In v2, `_checkpoint_segment` creates a `SourceText` row as a surrogate carrier for the `Translation` row, keyed with `notes="paragraph:{paragraph_id}"` and `model="pipeline_v2"`. The canonical translation output lives in `Paragraph.translated_text`. The `Translation` row is supplementary and stores `confidence_log`. If `SourceText` insertion fails for any reason, the `Paragraph` row is still updated (fire-and-forget on the Translation row).

### EPUB export path

Output: `DATA_DIR / "exports" / f"{book_id}_translated.epub"`

`DATA_DIR` comes from `app.core.paths.DATA_DIR` which reads `$HIME_DATA_DIR` env var. The `exports/` subdirectory is created with `mkdir(parents=True, exist_ok=True)` if it doesn't exist.

---

## Definition of Done

- [ ] `test_runner_v2.py` — all 7 tests pass
- [ ] `uv run pytest` — no regressions in existing test suite
- [ ] `run_pipeline_v2` importable from `app.pipeline`
- [ ] `export_book` importable from `app.services.epub_export_service`
- [ ] `postprocess_book`, `reassemble_chapter` importable from `app.pipeline.postprocessor`
- [ ] Retry loop tested explicitly: 2 retries → 3 polish calls; always-retry → stops at 3 retries and emits `pipeline_complete`
- [ ] DB checkpoint tested: `_checkpoint_segment` called once per segment with correct args
- [ ] EPUB export tested: file written at expected path (mocked `to_thread`)
- [ ] Old `runner.py` untouched — `run_pipeline` still importable
- [ ] Stubs created for any missing WS-A/B/C/D modules (prevents import errors)
- [ ] Commit created with conventional commit message
