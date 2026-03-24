from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(settings.db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


_PIPELINE_COLS = [
    ("stage1_gemma_output",    "TEXT"),
    ("stage1_deepseek_output", "TEXT"),
    ("stage1_qwen32b_output",  "TEXT"),
    ("consensus_output",       "TEXT"),
    ("stage2_output",          "TEXT"),
    ("final_output",           "TEXT"),
    ("pipeline_duration_ms",   "INTEGER"),
    ("current_stage",          "TEXT"),
]


async def init_db() -> None:
    """Create all tables on startup and apply inline column migrations."""
    from sqlalchemy import text  # local import to avoid circular at module level

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Add new pipeline columns to an existing translations table if missing.
        # SQLAlchemy create_all never adds columns to existing tables.
        rows = (await conn.execute(text("PRAGMA table_info(translations)"))).fetchall()
        existing = {r[1] for r in rows}
        for col, dtype in _PIPELINE_COLS:
            if col not in existing:
                await conn.execute(
                    text(f"ALTER TABLE translations ADD COLUMN {col} {dtype}")
                )

        # Add is_front_matter column to chapters if missing
        rows_ch = (await conn.execute(text("PRAGMA table_info(chapters)"))).fetchall()
        existing_ch = {r[1] for r in rows_ch}
        if "is_front_matter" not in existing_ch:
            await conn.execute(text("ALTER TABLE chapters ADD COLUMN is_front_matter BOOLEAN DEFAULT 0"))

        # Seed default settings (INSERT OR IGNORE preserves user changes)
        await conn.execute(text(
            "INSERT OR IGNORE INTO settings (key, value) VALUES "
            "('epub_watch_folder', 'C:/Projekte/Hime/data/epubs/'), "
            "('auto_scan_interval', '60')"
        ))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        yield session
