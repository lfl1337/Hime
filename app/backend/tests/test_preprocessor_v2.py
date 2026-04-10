"""Tests for pipeline v2 Pre-Processing — WS-A.

Run from: N:/Projekte/NiN/Hime/.worktrees/pipeline-v2/app/backend/
Command:  uv run pytest tests/test_preprocessor_v2.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from dataclasses import fields as dc_fields
from unittest.mock import AsyncMock, MagicMock, patch


# ── Task 1: PreprocessedSegment shape ──────────────────────────────────────

def test_preprocessed_segment_has_required_fields():
    """PreprocessedSegment must expose all five fields the Stage 1 runner needs."""
    from app.pipeline.preprocessor import PreprocessedSegment
    field_names = {f.name for f in dc_fields(PreprocessedSegment)}
    assert "paragraph_id"     in field_names
    assert "source_jp"        in field_names
    assert "mecab_tokens"     in field_names
    assert "glossary_context" in field_names
    assert "rag_context"      in field_names


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


# ── Task 3: preprocess_book edge cases ────────────────────────────────────

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
    mock_session.execute = AsyncMock(return_value=mock_result)

    # GlossaryService.get_or_create_for_book — patch so we don't hit DB
    with patch(
        "app.pipeline.preprocessor.GlossaryService.get_or_create_for_book",
        new_callable=AsyncMock,
        return_value=MagicMock(id=1),
    ):
        result = await preprocess_book(book_id=1, session=mock_session)

    assert result == []


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
