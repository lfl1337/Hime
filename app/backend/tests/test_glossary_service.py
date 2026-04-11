"""Tests for GlossaryService — CRUD, auto-extract, prompt-formatting."""
import pytest

from app.database import AsyncSessionLocal, init_db
from app.models import Book
from app.services.glossary_service import GlossaryService

# Book ids used by glossary tests below. Each test creates a glossary
# referencing one of these ids; with FK enforcement (Phase 1 W2), the parent
# Book rows MUST exist first — SQLite will reject orphan glossary inserts.
_FIXTURE_BOOK_IDS = [42, 43, 44, 45, 46]


@pytest.fixture(autouse=True)
async def _db():
    await init_db()
    # Seed the parent Book rows the glossary tests depend on.
    # Idempotent: skip rows that already exist (autouse fixture runs per-test).
    async with AsyncSessionLocal() as session:
        for book_id in _FIXTURE_BOOK_IDS:
            existing = await session.get(Book, book_id)
            if existing is None:
                session.add(Book(
                    id=book_id,
                    title=f"Glossary test fixture {book_id}",
                    author="test",
                    file_path=f"/tmp/glossary_fixture_book_{book_id}.epub",
                ))
        await session.commit()


@pytest.mark.asyncio
async def test_get_or_create_glossary_for_book():
    async with AsyncSessionLocal() as session:
        svc = GlossaryService(session)
        g = await svc.get_or_create_for_book(book_id=42)
        assert g.book_id == 42
        assert g.id is not None


@pytest.mark.asyncio
async def test_add_term_persists():
    async with AsyncSessionLocal() as session:
        svc = GlossaryService(session)
        g = await svc.get_or_create_for_book(book_id=43)
        term = await svc.add_term(
            glossary_id=g.id, source_term="アイコ", target_term="Aiko",
            category="name", notes=None,
        )
        assert term.id is not None

        terms = await svc.list_terms(glossary_id=g.id)
        sources = {t.source_term for t in terms}
        assert "アイコ" in sources


@pytest.mark.asyncio
async def test_format_for_prompt_only_includes_present_terms():
    async with AsyncSessionLocal() as session:
        svc = GlossaryService(session)
        g = await svc.get_or_create_for_book(book_id=44)
        await svc.add_term(g.id, "アイコ", "Aiko", "name", None)
        await svc.add_term(g.id, "東京", "Tokyo", "place", None)
        # Only Aiko appears in the source text
        formatted = await svc.format_for_prompt(g.id, source_text="アイコは家に帰った。")
        assert "Aiko" in formatted
        assert "Tokyo" not in formatted


@pytest.mark.asyncio
async def test_format_for_prompt_returns_empty_when_no_matches():
    async with AsyncSessionLocal() as session:
        svc = GlossaryService(session)
        g = await svc.get_or_create_for_book(book_id=45)
        await svc.add_term(g.id, "アイコ", "Aiko", "name", None)
        formatted = await svc.format_for_prompt(g.id, source_text="無関係な文。")
        assert formatted == ""


@pytest.mark.asyncio
async def test_auto_extract_returns_proper_noun_candidates():
    async with AsyncSessionLocal() as session:
        svc = GlossaryService(session)
        g = await svc.get_or_create_for_book(book_id=46)
        added = await svc.auto_extract_from_translation(
            glossary_id=g.id,
            source_text="アイコは東京に住んでいる。アイコは学生だ。",
            translated_text="Aiko lives in Tokyo. Aiko is a student.",
        )
        assert any("アイコ" in t.source_term for t in added)
