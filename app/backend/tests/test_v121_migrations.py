"""Tests for v1.2.1 inline migrations (paragraphs/books/translations columns + glossary tables)."""
import pytest
from sqlalchemy import text

from app.database import engine, init_db


@pytest.mark.asyncio
async def test_paragraphs_has_verification_result():
    await init_db()
    async with engine.connect() as conn:
        rows = (await conn.execute(text("PRAGMA table_info(paragraphs)"))).fetchall()
        cols = {r[1] for r in rows}
        assert "verification_result" in cols
        assert "is_reviewed" in cols
        assert "reviewed_at" in cols
        assert "reviewer_notes" in cols


@pytest.mark.asyncio
async def test_books_has_series_columns():
    await init_db()
    async with engine.connect() as conn:
        rows = (await conn.execute(text("PRAGMA table_info(books)"))).fetchall()
        cols = {r[1] for r in rows}
        assert "series_id" in cols
        assert "series_title" in cols


@pytest.mark.asyncio
async def test_translations_has_confidence_log():
    await init_db()
    async with engine.connect() as conn:
        rows = (await conn.execute(text("PRAGMA table_info(translations)"))).fetchall()
        cols = {r[1] for r in rows}
        assert "confidence_log" in cols


@pytest.mark.asyncio
async def test_glossary_tables_exist():
    await init_db()
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('glossaries','glossary_terms')"
        ))).fetchall()
        names = {r[0] for r in rows}
        assert names == {"glossaries", "glossary_terms"}


@pytest.mark.asyncio
async def test_glossary_indexes_exist():
    await init_db()
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_glossary%'"
        ))).fetchall()
        names = {r[0] for r in rows}
        assert "idx_glossary_terms_glossary" in names
        assert "idx_glossary_terms_source" in names
