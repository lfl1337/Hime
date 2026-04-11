"""Verify that every SQLAlchemy DB connection has foreign_keys enforcement enabled."""
import pytest
from sqlalchemy import text

# Import models so Base.metadata is populated before the session-scoped
# autouse fixture in conftest.py calls init_db(). Without this, running
# this test file in isolation leaves Base.metadata empty, and init_db's
# inline migrations ALTER a table that create_all never created.
from app import models  # noqa: F401
from app.database import AsyncSessionLocal


@pytest.mark.asyncio
async def test_foreign_keys_enabled_on_new_session():
    """Every new session must report PRAGMA foreign_keys = 1."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("PRAGMA foreign_keys"))
        value = result.scalar()
        assert value == 1, f"PRAGMA foreign_keys should be 1 (ON), got {value}"


@pytest.mark.asyncio
async def test_foreign_key_enforcement_rejects_orphan():
    """Orphan Chapter inserts must raise IntegrityError under FK enforcement.

    Uses the shared AsyncSessionLocal (same DB as the conftest autouse init_db
    fixture). The insert is rolled back on IntegrityError so no orphan survives
    the test. NOTE: this does NOT isolate to a tmp_path — a Phase 3 follow-up
    will fix the conftest to target a temp DB so production files can't be
    touched by test runs.
    """
    from sqlalchemy.exc import IntegrityError
    from app.models import Chapter

    async with AsyncSessionLocal() as session:
        orphan = Chapter(
            book_id=99999999,
            chapter_index=0,
            title="test-orphan-chapter",
            total_paragraphs=0,
            translated_paragraphs=0,
            status="pending",
        )
        session.add(orphan)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
