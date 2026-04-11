# Pipeline v2 WS-A: Pre-Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take an already-imported EPUB (Book/Chapter/Paragraph records in SQLite) and produce a list of `PreprocessedSegment` objects — each carrying MeCab tokens, matching glossary context, and RAG context — ready for Stage 1 translation to consume.

**Architecture:** A new `pipeline/preprocessor.py` module contains all business logic. It reads Paragraphs via SQLAlchemy async, calls the existing `LexiconService`, `GlossaryService`, and `retrieve_top_k`/`format_rag_context` from the RAG layer, and returns a plain `list[PreprocessedSegment]`. A thin new FastAPI router `routers/pipeline.py` exposes `POST /api/v1/pipeline/{book_id}/preprocess` and delegates to this module. No changes to the existing `pipeline/runner.py` in this workstream.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 async, Pydantic v2, `mecab-python3 + unidic-lite` (already in pyproject.toml), `pytest + pytest-asyncio` (asyncio_mode = auto), `sqlite-vec` (already in pyproject.toml for RAG)

---

## Constraints (read first)

1. **No model downloads.** `embed_texts()` calls `sentence_transformers` + bge-m3. If the model is absent and `HIME_ALLOW_DOWNLOADS=false`, `retrieve_top_k` returns `[]` — the preprocessor must tolerate that gracefully.
2. **Do not touch `pipeline/runner.py`** — that is WS-E's responsibility.
3. **MeCab / JMdict are heavy.** Tests that call `LexiconService().translate()` will work only if MeCab + unidic-lite are installed in the test environment. The tests in this plan use `monkeypatch` to avoid hitting MeCab in CI; a separate integration marker is noted where real MeCab is needed.
4. **Paragraphs are ordered** by `chapter.chapter_index ASC, paragraph.paragraph_index ASC`. Use a joined `select` with `order_by` — never rely on insertion order.
5. **`Book.series_id` can be `None`** (e.g. standalone novels with no RAG index). `retrieve_top_k` already handles a missing `.db` file with `return []`, so no extra guard is needed in the preprocessor beyond passing `series_id=None` safely (wrap in `if book.series_id is not None`).
6. **`Glossary` is per-book.** Use `GlossaryService(session).get_or_create_for_book(book_id)` to always get a valid glossary id, even if no terms exist yet.
7. **The router must call `sanitize_text()`** on any user-supplied string path parameters per project security policy (`app/backend/app/utils/sanitize.py`). `book_id` is an integer so no sanitization is needed beyond FastAPI's type coercion.
8. **Batch embedding for performance.** Embedding one paragraph at a time is slow. Embed all paragraphs in a single `embed_texts(texts)` call, then query the RAG store per-paragraph using the pre-computed vectors directly via `SeriesStore.query()`. This avoids loading the bge-m3 model N times.

---

## File Map

### New files

| Path | Responsibility |
|------|----------------|
| `app/backend/app/pipeline/preprocessor.py` | `PreprocessedSegment` dataclass + `preprocess_book()` async function |
| `app/backend/app/routers/pipeline.py` | `POST /api/v1/pipeline/{book_id}/preprocess` endpoint |
| `app/backend/tests/test_preprocessor_v2.py` | Unit + integration tests for preprocessor and router |

### Modified files

| Path | What changes |
|------|-------------|
| `app/backend/app/main.py` | Import and mount `pipeline_router` under `/api/v1` |

### Files read but NOT modified

| Path | Why you need to read it |
|------|------------------------|
| `app/backend/app/models.py` | `Book`, `Chapter`, `Paragraph`, `Glossary`, `GlossaryTerm` ORM shapes |
| `app/backend/app/rag/retriever.py` | `retrieve_top_k(series_id, query_text, top_k)` and `format_rag_context(chunks)` signatures |
| `app/backend/app/rag/store.py` | `SeriesStore(db_path).query(query_embedding, top_k)` — used for batch path |
| `app/backend/app/rag/embeddings.py` | `embed_texts(texts) -> list[list[float]]` |
| `app/backend/app/services/lexicon_service.py` | `LexiconService().translate(text) -> LexiconResult` and `LexiconToken` fields |
| `app/backend/app/services/glossary_service.py` | `GlossaryService(session).get_or_create_for_book(book_id)` and `.format_for_prompt(glossary_id, source_text)` |
| `app/backend/app/database.py` | `AsyncSessionLocal`, `get_session` dependency |
| `app/backend/app/core/paths.py` | `RAG_DIR` constant |

---

## Task 1: Write the failing test for `PreprocessedSegment` dataclass

**Files:**
- Create: `app/backend/tests/test_preprocessor_v2.py`

- [ ] **Step 1.1: Create the test file with the dataclass shape test**

Create `N:/Projekte/NiN/Hime/app/backend/tests/test_preprocessor_v2.py`:

```python
"""Tests for pipeline v2 Pre-Processing — WS-A.

Run from: N:/Projekte/NiN/Hime/app/backend/
Command:  uv run pytest tests/test_preprocessor_v2.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from dataclasses import fields as dc_fields


# ── Task 1: PreprocessedSegment shape ──────────────────────────────────────

def test_preprocessed_segment_has_required_fields():
    """PreprocessedSegment must expose all five fields the Stage 1 runner needs."""
    from app.pipeline.preprocessor import PreprocessedSegment
    field_names = {f.name for f in dc_fields(PreprocessedSegment)}
    assert "paragraph_id"    in field_names
    assert "source_jp"       in field_names
    assert "mecab_tokens"    in field_names
    assert "glossary_context" in field_names
    assert "rag_context"     in field_names


def test_preprocessed_segment_instantiation():
    """PreprocessedSegment can be constructed with minimal data."""
    from app.pipeline.preprocessor import PreprocessedSegment
    seg = PreprocessedSegment(
        paragraph_id=1,
        source_jp="テスト",
        mecab_tokens=[],
        glossary_context="",
        rag_context="",
    )
    assert seg.paragraph_id == 1
    assert seg.source_jp == "テスト"
    assert seg.mecab_tokens == []
    assert seg.glossary_context == ""
    assert seg.rag_context == ""
```

- [ ] **Step 1.2: Run the test and confirm it fails**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py::test_preprocessed_segment_has_required_fields tests/test_preprocessor_v2.py::test_preprocessed_segment_instantiation -v
```

Expected output: `FAILED` / `ModuleNotFoundError: No module named 'app.pipeline.preprocessor'`

---

## Task 2: Implement `PreprocessedSegment`

**Files:**
- Create: `app/backend/app/pipeline/preprocessor.py`

- [ ] **Step 2.1: Create the preprocessor module with the dataclass**

Create `N:/Projekte/NiN/Hime/app/backend/app/pipeline/preprocessor.py`:

```python
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
```

- [ ] **Step 2.2: Run the dataclass tests and confirm they pass**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py::test_preprocessed_segment_has_required_fields tests/test_preprocessor_v2.py::test_preprocessed_segment_instantiation -v
```

Expected output: `2 passed`

- [ ] **Step 2.3: Commit**

```bash
cd N:/Projekte/NiN/Hime/app/backend
git add app/pipeline/preprocessor.py tests/test_preprocessor_v2.py
git commit -m "feat(pipeline/wsa): add PreprocessedSegment dataclass + preprocessor skeleton"
```

---

## Task 3: Write failing tests for `preprocess_book` — book-not-found and empty-paragraphs

**Files:**
- Modify: `app/backend/tests/test_preprocessor_v2.py`

- [ ] **Step 3.1: Add the two edge-case tests**

Append the following to `N:/Projekte/NiN/Hime/app/backend/tests/test_preprocessor_v2.py`:

```python
# ── Task 3: preprocess_book edge cases ────────────────────────────────────

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_preprocess_book_raises_on_missing_book():
    """preprocess_book raises ValueError when book_id does not exist."""
    from app.pipeline.preprocessor import preprocess_book

    mock_session = AsyncMock()
    mock_session.get.return_value = None  # Book not found

    with pytest.raises(ValueError, match="Book 9999 not found"):
        await preprocess_book(book_id=9999, session=mock_session)


@pytest.mark.asyncio
async def test_preprocess_book_returns_empty_list_when_no_paragraphs():
    """preprocess_book returns [] when the book has no non-skipped paragraphs."""
    from app.pipeline.preprocessor import preprocess_book
    from app.models import Book

    fake_book = Book(id=1, title="Empty Book", file_path="/tmp/empty.epub")
    fake_book.series_id = None

    mock_session = AsyncMock()
    mock_session.get.return_value = fake_book

    # Simulate execute() returning zero rows
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    # GlossaryService.get_or_create_for_book — patch so we don't hit DB
    with patch(
        "app.pipeline.preprocessor.GlossaryService.get_or_create_for_book",
        new_callable=AsyncMock,
        return_value=MagicMock(id=1),
    ):
        result = await preprocess_book(book_id=1, session=mock_session)

    assert result == []
```

- [ ] **Step 3.2: Run just these two tests and confirm they fail**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py::test_preprocess_book_raises_on_missing_book tests/test_preprocessor_v2.py::test_preprocess_book_returns_empty_list_when_no_paragraphs -v
```

Expected: `FAILED` — the mock session's `execute()` call raises or the function logic doesn't exist yet for the empty-paragraphs path. (If these happen to pass already, proceed to Task 4.)

- [ ] **Step 3.3: Verify both tests pass with the implementation already written in Task 2**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py::test_preprocess_book_raises_on_missing_book tests/test_preprocessor_v2.py::test_preprocess_book_returns_empty_list_when_no_paragraphs -v
```

Expected: `2 passed`

Note: If the `execute` mock path raises `TypeError`, the issue is that `AsyncMock.execute()` needs to return an awaitable. Adjust: `mock_session.execute = AsyncMock(return_value=mock_result)`.

- [ ] **Step 3.4: Commit**

```bash
cd N:/Projekte/NiN/Hime/app/backend
git add tests/test_preprocessor_v2.py
git commit -m "test(pipeline/wsa): edge cases — missing book + empty paragraph list"
```

---

## Task 4: Write failing test for the happy path — lexicon/glossary/RAG all mocked

**Files:**
- Modify: `app/backend/tests/test_preprocessor_v2.py`

- [ ] **Step 4.1: Add the happy-path test**

Append the following to `N:/Projekte/NiN/Hime/app/backend/tests/test_preprocessor_v2.py`:

```python
# ── Task 4: preprocess_book happy path (all dependencies mocked) ───────────

@pytest.mark.asyncio
async def test_preprocess_book_happy_path_no_rag():
    """
    preprocess_book returns one PreprocessedSegment per paragraph.
    All heavy dependencies (MeCab, RAG embeddings, GlossaryService) are mocked.
    book.series_id is None so no RAG is attempted.
    """
    from app.pipeline.preprocessor import preprocess_book, PreprocessedSegment
    from app.models import Book, Chapter, Paragraph
    from app.services.lexicon_service import LexiconResult, LexiconToken

    # ── Fake DB objects ────────────────────────────────────────────────────
    fake_book = Book(id=10, title="Test Book", file_path="/tmp/test.epub")
    fake_book.series_id = None  # No RAG

    fake_para1 = Paragraph(
        id=101, chapter_id=1, paragraph_index=0,
        source_text="彼女は笑った。", is_skipped=False,
    )
    fake_para2 = Paragraph(
        id=102, chapter_id=1, paragraph_index=1,
        source_text="空が青い。", is_skipped=False,
    )

    mock_session = AsyncMock()
    mock_session.get.return_value = fake_book

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_para1, fake_para2]
    mock_session.execute = AsyncMock(return_value=mock_result)

    # ── Fake lexicon result ────────────────────────────────────────────────
    fake_token = LexiconToken(surface="彼女", pos="名詞", glosses=["she", "her"])
    fake_lex = LexiconResult(
        tokens=[fake_token],
        literal_translation="she laughed",
        unknown_tokens=[],
        confidence=0.9,
    )

    # ── Patch GlossaryService and LexiconService ───────────────────────────
    with (
        patch(
            "app.pipeline.preprocessor.GlossaryService.get_or_create_for_book",
            new_callable=AsyncMock,
            return_value=MagicMock(id=5),
        ),
        patch(
            "app.pipeline.preprocessor.GlossaryService.format_for_prompt",
            new_callable=AsyncMock,
            return_value="Glossary (use these renderings consistently):\n  彼女 → she [pronoun]",
        ),
        patch(
            "app.pipeline.preprocessor.LexiconService.translate",
            return_value=fake_lex,
        ),
    ):
        segments = await preprocess_book(book_id=10, session=mock_session)

    assert len(segments) == 2
    assert all(isinstance(s, PreprocessedSegment) for s in segments)

    s0, s1 = segments
    assert s0.paragraph_id == 101
    assert s0.source_jp == "彼女は笑った。"
    assert len(s0.mecab_tokens) == 1
    assert s0.mecab_tokens[0].surface == "彼女"
    assert "彼女" in s0.glossary_context
    assert s0.rag_context == ""  # No RAG — series_id is None

    assert s1.paragraph_id == 102
    assert s1.source_jp == "空が青い。"


@pytest.mark.asyncio
async def test_preprocess_book_graceful_lexicon_failure():
    """
    When LexiconService.translate raises, the segment still has mecab_tokens=[]
    and processing continues for subsequent paragraphs.
    """
    from app.pipeline.preprocessor import preprocess_book
    from app.models import Book, Paragraph

    fake_book = Book(id=20, title="Book20", file_path="/tmp/b20.epub")
    fake_book.series_id = None

    fake_para = Paragraph(
        id=201, chapter_id=2, paragraph_index=0,
        source_text="テスト。", is_skipped=False,
    )

    mock_session = AsyncMock()
    mock_session.get.return_value = fake_book
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_para]
    mock_session.execute = AsyncMock(return_value=mock_result)

    def _crash(text):
        raise RuntimeError("MeCab not available")

    with (
        patch(
            "app.pipeline.preprocessor.GlossaryService.get_or_create_for_book",
            new_callable=AsyncMock,
            return_value=MagicMock(id=6),
        ),
        patch(
            "app.pipeline.preprocessor.GlossaryService.format_for_prompt",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "app.pipeline.preprocessor.LexiconService.translate",
            side_effect=_crash,
        ),
    ):
        segments = await preprocess_book(book_id=20, session=mock_session)

    assert len(segments) == 1
    assert segments[0].mecab_tokens == []
```

- [ ] **Step 4.2: Run these tests to confirm they pass**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py::test_preprocess_book_happy_path_no_rag tests/test_preprocessor_v2.py::test_preprocess_book_graceful_lexicon_failure -v
```

Expected: `2 passed`

If the `patch` paths for `GlossaryService.get_or_create_for_book` and `.format_for_prompt` raise an `AttributeError`, replace with explicit module-level patches:

```python
patch("app.pipeline.preprocessor.GlossaryService") as MockGloss
```
and configure `MockGloss.return_value.get_or_create_for_book = AsyncMock(return_value=MagicMock(id=5))` etc.

- [ ] **Step 4.3: Commit**

```bash
cd N:/Projekte/NiN/Hime/app/backend
git add tests/test_preprocessor_v2.py
git commit -m "test(pipeline/wsa): happy path + graceful lexicon failure coverage"
```

---

## Task 5: Write failing test for RAG batch embedding path

**Files:**
- Modify: `app/backend/tests/test_preprocessor_v2.py`

- [ ] **Step 5.1: Add RAG path test**

Append the following to `N:/Projekte/NiN/Hime/app/backend/tests/test_preprocessor_v2.py`:

```python
# ── Task 5: preprocess_book with RAG (mocked store + embeddings) ───────────

@pytest.mark.asyncio
async def test_preprocess_book_with_rag_context(tmp_path):
    """
    When book.series_id is set AND a RAG .db file exists, rag_context is populated
    on each segment. embed_texts and SeriesStore.query are both mocked.
    """
    from app.pipeline.preprocessor import preprocess_book
    from app.models import Book, Paragraph
    from app.services.lexicon_service import LexiconResult, LexiconToken

    # Create a fake series .db file so the path-existence check passes
    fake_series_id = 42
    fake_db = tmp_path / f"series_{fake_series_id}.db"
    fake_db.touch()

    fake_book = Book(id=30, title="Book30", file_path="/tmp/b30.epub")
    fake_book.series_id = fake_series_id

    fake_para = Paragraph(
        id=301, chapter_id=3, paragraph_index=0,
        source_text="彼女は走った。", is_skipped=False,
    )

    mock_session = AsyncMock()
    mock_session.get.return_value = fake_book
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_para]
    mock_session.execute = AsyncMock(return_value=mock_result)

    fake_token = LexiconToken(surface="彼女", pos="名詞", glosses=["she"])
    fake_lex = LexiconResult(
        tokens=[fake_token], literal_translation="she ran",
        unknown_tokens=[], confidence=0.95,
    )

    fake_chunks = [
        {
            "book_id": 30, "chapter_id": 3, "paragraph_id": 300,
            "source_text": "彼女は笑った。", "translated_text": "She laughed.",
            "distance": 0.1,
        }
    ]

    mock_store = MagicMock()
    mock_store.query.return_value = fake_chunks

    with (
        patch("app.pipeline.preprocessor.RAG_DIR", tmp_path),
        patch(
            "app.pipeline.preprocessor.embed_texts",
            return_value=[[0.1] * 1024],
        ),
        patch(
            "app.pipeline.preprocessor.SeriesStore",
            return_value=mock_store,
        ),
        patch(
            "app.pipeline.preprocessor.GlossaryService.get_or_create_for_book",
            new_callable=AsyncMock,
            return_value=MagicMock(id=7),
        ),
        patch(
            "app.pipeline.preprocessor.GlossaryService.format_for_prompt",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "app.pipeline.preprocessor.LexiconService.translate",
            return_value=fake_lex,
        ),
    ):
        segments = await preprocess_book(book_id=30, session=mock_session)

    assert len(segments) == 1
    seg = segments[0]
    assert seg.paragraph_id == 301
    # RAG context must reference the matched paragraph
    assert "She laughed" in seg.rag_context
    # embed_texts was called once with all source texts
    # SeriesStore.query was called once per paragraph
    mock_store.query.assert_called_once()
    mock_store.close.assert_called_once()


@pytest.mark.asyncio
async def test_preprocess_book_no_rag_when_db_absent(tmp_path):
    """
    When book.series_id is set but no .db file exists in RAG_DIR,
    rag_context is '' and embed_texts is never called.
    """
    from app.pipeline.preprocessor import preprocess_book
    from app.models import Book, Paragraph
    from app.services.lexicon_service import LexiconResult

    fake_book = Book(id=40, title="Book40", file_path="/tmp/b40.epub")
    fake_book.series_id = 99  # series 99 has no .db

    fake_para = Paragraph(
        id=401, chapter_id=4, paragraph_index=0,
        source_text="空。", is_skipped=False,
    )

    mock_session = AsyncMock()
    mock_session.get.return_value = fake_book
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_para]
    mock_session.execute = AsyncMock(return_value=mock_result)

    embed_mock = MagicMock()

    with (
        patch("app.pipeline.preprocessor.RAG_DIR", tmp_path),
        patch("app.pipeline.preprocessor.embed_texts", embed_mock),
        patch(
            "app.pipeline.preprocessor.GlossaryService.get_or_create_for_book",
            new_callable=AsyncMock,
            return_value=MagicMock(id=8),
        ),
        patch(
            "app.pipeline.preprocessor.GlossaryService.format_for_prompt",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "app.pipeline.preprocessor.LexiconService.translate",
            return_value=LexiconResult(
                tokens=[], literal_translation="", unknown_tokens=[], confidence=0.0,
            ),
        ),
    ):
        segments = await preprocess_book(book_id=40, session=mock_session)

    assert len(segments) == 1
    assert segments[0].rag_context == ""
    embed_mock.assert_not_called()
```

- [ ] **Step 5.2: Run these tests**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py::test_preprocess_book_with_rag_context tests/test_preprocessor_v2.py::test_preprocess_book_no_rag_when_db_absent -v
```

Expected: `2 passed`

- [ ] **Step 5.3: Commit**

```bash
cd N:/Projekte/NiN/Hime/app/backend
git add tests/test_preprocessor_v2.py
git commit -m "test(pipeline/wsa): RAG batch embedding path + absent-db short-circuit"
```

---

## Task 6: Write failing test for the router endpoint

**Files:**
- Modify: `app/backend/tests/test_preprocessor_v2.py`

- [ ] **Step 6.1: Add router tests**

Append the following to `N:/Projekte/NiN/Hime/app/backend/tests/test_preprocessor_v2.py`:

```python
# ── Task 6: POST /api/v1/pipeline/{book_id}/preprocess router ─────────────

from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_pipeline_preprocess_endpoint_returns_200(tmp_path):
    """
    POST /api/v1/pipeline/1/preprocess returns 200 with segment_count and sample.
    preprocess_book is mocked so no DB or model is needed.
    """
    from app.pipeline.preprocessor import PreprocessedSegment
    from app.services.lexicon_service import LexiconToken

    fake_seg = PreprocessedSegment(
        paragraph_id=1,
        source_jp="テスト。",
        mecab_tokens=[LexiconToken(surface="テスト", pos="名詞", glosses=["test"])],
        glossary_context="",
        rag_context="",
    )

    with patch(
        "app.routers.pipeline.preprocess_book",
        new_callable=AsyncMock,
        return_value=[fake_seg],
    ):
        # Import app lazily to avoid side-effects at module load
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/pipeline/1/preprocess")

    assert resp.status_code == 200
    body = resp.json()
    assert body["segment_count"] == 1
    assert "sample" in body
    sample = body["sample"]
    assert sample[0]["paragraph_id"] == 1
    assert sample[0]["source_jp"] == "テスト。"
    assert "mecab_token_count" in sample[0]
    assert "glossary_context" in sample[0]
    assert "rag_context" in sample[0]


@pytest.mark.asyncio
async def test_pipeline_preprocess_endpoint_404_on_missing_book():
    """
    POST /api/v1/pipeline/9999/preprocess returns 404 when the book does not exist.
    """
    with patch(
        "app.routers.pipeline.preprocess_book",
        new_callable=AsyncMock,
        side_effect=ValueError("Book 9999 not found"),
    ):
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/pipeline/9999/preprocess")

    assert resp.status_code == 404
    assert "9999" in resp.json()["detail"]
```

- [ ] **Step 6.2: Run router tests and confirm they fail**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py::test_pipeline_preprocess_endpoint_returns_200 tests/test_preprocessor_v2.py::test_pipeline_preprocess_endpoint_404_on_missing_book -v
```

Expected: `FAILED` / `404` or `ImportError: cannot import name 'pipeline' from 'app.routers'`

---

## Task 7: Implement the router

**Files:**
- Create: `app/backend/app/routers/pipeline.py`

- [ ] **Step 7.1: Create the router file**

Create `N:/Projekte/NiN/Hime/app/backend/app/routers/pipeline.py`:

```python
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
```

- [ ] **Step 7.2: Run the router tests and confirm they pass**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py::test_pipeline_preprocess_endpoint_returns_200 tests/test_preprocessor_v2.py::test_pipeline_preprocess_endpoint_404_on_missing_book -v
```

Expected: `2 passed`

- [ ] **Step 7.3: Commit**

```bash
cd N:/Projekte/NiN/Hime/app/backend
git add app/routers/pipeline.py tests/test_preprocessor_v2.py
git commit -m "feat(pipeline/wsa): add pipeline router with preprocess endpoint"
```

---

## Task 8: Mount the router in `main.py`

**Files:**
- Modify: `app/backend/app/main.py`

- [ ] **Step 8.1: Add the import and router mount**

Open `N:/Projekte/NiN/Hime/app/backend/app/main.py`.

After the line:
```python
from .routers import rag as rag_router
```

Add:
```python
from .routers import pipeline as pipeline_router
```

After the line:
```python
app.include_router(rag_router.router, prefix="/api/v1")
```

Add:
```python
app.include_router(pipeline_router.router, prefix="/api/v1")
```

The full relevant section should look like:

```python
from .routers import rag as rag_router
from .routers import pipeline as pipeline_router
# ... (existing imports continue)

# Routers
app.include_router(texts.router, prefix="/api/v1")
app.include_router(translations.router, prefix="/api/v1")
app.include_router(training.router, prefix="/api/v1")
app.include_router(epub_router.router, prefix="/api/v1")
app.include_router(hardware_router.router, prefix="/api/v1")
app.include_router(compare_router.router, prefix="/api/v1")
app.include_router(models_router.router, prefix="/api/v1")
app.include_router(review_router.router, prefix="/api/v1")
app.include_router(lexicon_router.router, prefix="/api/v1")
app.include_router(verify_router.router, prefix="/api/v1")
app.include_router(glossary_router.router, prefix="/api/v1")
app.include_router(flywheel_router.router, prefix="/api/v1")
app.include_router(rag_router.router, prefix="/api/v1")
app.include_router(pipeline_router.router, prefix="/api/v1")
app.include_router(streaming.router)  # WebSocket — no /api/v1 prefix
```

- [ ] **Step 8.2: Verify the router is reachable via the test client**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py -v
```

Expected: All tests in the file pass.

- [ ] **Step 8.3: Confirm the OpenAPI spec includes the new endpoint**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run python -c "
from app.main import app
import json
routes = [r.path for r in app.routes]
assert any('/pipeline/' in p for p in routes), f'pipeline route not found in {routes}'
print('OK — pipeline route registered')
"
```

Expected: `OK — pipeline route registered`

- [ ] **Step 8.4: Commit**

```bash
cd N:/Projekte/NiN/Hime/app/backend
git add app/main.py
git commit -m "feat(pipeline/wsa): mount pipeline router in main.py"
```

---

## Task 9: Full test-suite run and final integration smoke test

**Files:** No changes — verification only.

- [ ] **Step 9.1: Run the full WS-A test file**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/test_preprocessor_v2.py -v --tb=short
```

Expected output (all 10 tests pass):
```
tests/test_preprocessor_v2.py::test_preprocessed_segment_has_required_fields PASSED
tests/test_preprocessor_v2.py::test_preprocessed_segment_instantiation PASSED
tests/test_preprocessor_v2.py::test_preprocess_book_raises_on_missing_book PASSED
tests/test_preprocessor_v2.py::test_preprocess_book_returns_empty_list_when_no_paragraphs PASSED
tests/test_preprocessor_v2.py::test_preprocess_book_happy_path_no_rag PASSED
tests/test_preprocessor_v2.py::test_preprocess_book_graceful_lexicon_failure PASSED
tests/test_preprocessor_v2.py::test_preprocess_book_with_rag_context PASSED
tests/test_preprocessor_v2.py::test_preprocess_book_no_rag_when_db_absent PASSED
tests/test_preprocessor_v2.py::test_pipeline_preprocess_endpoint_returns_200 PASSED
tests/test_preprocessor_v2.py::test_pipeline_preprocess_endpoint_404_on_missing_book PASSED
```

- [ ] **Step 9.2: Run the entire existing test suite to confirm no regressions**

```bash
cd N:/Projekte/NiN/Hime/app/backend
uv run pytest tests/ -v --tb=short --ignore=tests/test_hime_rag_mcp.py 2>&1 | tail -30
```

(The MCP test is excluded because it requires a running server process.)

Expected: All pre-existing tests continue to pass. New tests: 10 passed.

- [ ] **Step 9.3: Commit the final state if there are any unstaged changes**

```bash
cd N:/Projekte/NiN/Hime/app/backend
git status
# If clean, skip. Otherwise:
git add -p
git commit -m "chore(pipeline/wsa): final WS-A cleanup — all 10 tests green"
```

---

## Integration Test (requires real MeCab + DB — run manually, not in CI)

The following is an **optional manual smoke test** that exercises the real MeCab, real SQLite, and the real glossary service. Run it only when the full dev environment is available.

```python
# Save as: app/backend/tests/test_preprocessor_v2_integration.py
# Run with: uv run pytest tests/test_preprocessor_v2_integration.py -v -m integration

import pytest
pytest.importorskip("MeCab")

@pytest.mark.asyncio
@pytest.mark.integration
async def test_preprocess_real_book_in_db():
    """
    Requires a real Book with chapters + paragraphs in the dev DB.
    Adjust book_id to a known imported book.
    """
    from app.database import AsyncSessionLocal, init_db
    from app.pipeline.preprocessor import preprocess_book

    await init_db()

    BOOK_ID = 1  # Change to an actual book_id in your dev DB

    async with AsyncSessionLocal() as session:
        segments = await preprocess_book(book_id=BOOK_ID, session=session)

    assert len(segments) > 0
    s = segments[0]
    assert s.paragraph_id > 0
    assert len(s.source_jp) > 0
    # MeCab must produce at least one token for a real JP paragraph
    assert len(s.mecab_tokens) > 0
    print(f"First segment: {s.source_jp[:40]!r} → {len(s.mecab_tokens)} tokens")
```

Mark this test in `pyproject.toml` to require the `integration` marker:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["integration: requires real dev environment (MeCab, DB, models)"]
```

---

## Summary of deliverables

| Artifact | Path |
|----------|------|
| Core module | `app/backend/app/pipeline/preprocessor.py` |
| API router | `app/backend/app/routers/pipeline.py` |
| Test suite | `app/backend/tests/test_preprocessor_v2.py` |
| main.py modification | `app/backend/app/main.py` (2 lines added) |

### Endpoint produced

```
POST /api/v1/pipeline/{book_id}/preprocess
  → 200 { "book_id": int, "segment_count": int, "sample": [...] }
  → 404 if book_id not in DB
```

### `PreprocessedSegment` shape (consumed by WS-B Stage 1 adapters)

```python
@dataclass
class PreprocessedSegment:
    paragraph_id: int           # FK → paragraphs.id
    source_jp: str              # Raw JP text from paragraphs.source_text
    mecab_tokens: list[LexiconToken]  # MeCab parse via LexiconService
    glossary_context: str       # Prompt-ready string from GlossaryService
    rag_context: str            # Prompt-ready string from format_rag_context()
```

### Data flow

```
Book (book_id)
  └─ Paragraphs (ordered by chapter_index, paragraph_index, is_skipped=False)
        ├─ LexiconService.translate(source_text) → mecab_tokens
        ├─ GlossaryService.format_for_prompt(glossary_id, source_text) → glossary_context
        └─ [if series_id + RAG .db exists]
             embed_texts([all source_texts]) → embeddings[]
             SeriesStore.query(embeddings[i], top_k=5) → chunks
             format_rag_context(chunks) → rag_context
  └─ list[PreprocessedSegment]  →  Stage 1 (WS-B)
```
