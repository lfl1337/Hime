from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(settings.db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _enable_sqlite_fks(dbapi_connection, connection_record):
    """Enable SQLite foreign key constraints on every new connection.

    SQLite disables FKs by default; this listener flips them on for every
    low-level DBAPI connection (including aiosqlite), and the PRAGMA persists
    for the lifetime of that connection.

    Guard: only runs for SQLite connections — avoids a syntax error if the
    engine is ever pointed at PostgreSQL or another dialect.
    """
    if "sqlite" not in type(dbapi_connection).__module__:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


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

_V121_PARAGRAPH_COLS = [
    ("verification_result", "TEXT"),
    ("is_reviewed",         "BOOLEAN DEFAULT 0"),
    ("reviewed_at",         "TIMESTAMP"),
    ("reviewer_notes",      "TEXT"),
]

_V121_BOOK_COLS = [
    ("series_id",    "INTEGER"),
    ("series_title", "TEXT"),
]

_V121_TRANSLATION_COLS = [
    ("confidence_log", "TEXT"),
]

_V200_PARAGRAPH_RETRY_COLS = [
    ("retry_count_fix_pass",      "INTEGER NOT NULL DEFAULT 0"),
    ("retry_count_full_pipeline", "INTEGER NOT NULL DEFAULT 0"),
    ("retry_flag",                "BOOLEAN NOT NULL DEFAULT 0"),
    ("aggregator_verdict",        "TEXT"),
    ("aggregator_instruction",    "TEXT"),
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

        # v1.2.1 + v2.0.0: paragraph columns
        rows_par = (await conn.execute(text("PRAGMA table_info(paragraphs)"))).fetchall()
        existing_par = {r[1] for r in rows_par}
        for col, dtype in _V121_PARAGRAPH_COLS + _V200_PARAGRAPH_RETRY_COLS:
            if col not in existing_par:
                await conn.execute(text(f"ALTER TABLE paragraphs ADD COLUMN {col} {dtype}"))

        # v1.2.1: book columns (series tracking)
        rows_book = (await conn.execute(text("PRAGMA table_info(books)"))).fetchall()
        existing_book = {r[1] for r in rows_book}
        for col, dtype in _V121_BOOK_COLS:
            if col not in existing_book:
                await conn.execute(text(f"ALTER TABLE books ADD COLUMN {col} {dtype}"))

        # v1.2.1: translation columns (confidence_log)
        rows_tr = (await conn.execute(text("PRAGMA table_info(translations)"))).fetchall()
        existing_tr = {r[1] for r in rows_tr}
        for col, dtype in _V121_TRANSLATION_COLS:
            if col not in existing_tr:
                await conn.execute(text(f"ALTER TABLE translations ADD COLUMN {col} {dtype}"))

        # v1.2.1: glossary tables
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS glossaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER REFERENCES books(id),
                series_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS glossary_terms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                glossary_id INTEGER NOT NULL REFERENCES glossaries(id),
                source_term TEXT NOT NULL,
                target_term TEXT NOT NULL,
                category TEXT,
                notes TEXT,
                occurrences INTEGER DEFAULT 0,
                is_locked BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_glossary_terms_glossary ON glossary_terms(glossary_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_glossary_terms_source ON glossary_terms(source_term)"
        ))

        # Create hardware_stats table if missing
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hardware_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                gpu_name TEXT,
                gpu_vram_used_mb INTEGER,
                gpu_vram_total_mb INTEGER,
                gpu_vram_pct REAL,
                gpu_utilization_pct INTEGER,
                gpu_memory_pct INTEGER,
                gpu_temp_celsius INTEGER,
                gpu_power_draw_w REAL,
                gpu_power_limit_w REAL,
                gpu_clock_mhz INTEGER,
                gpu_max_clock_mhz INTEGER,
                cpu_utilization_pct REAL,
                cpu_freq_mhz REAL,
                cpu_core_count INTEGER,
                ram_used_gb REAL,
                ram_total_gb REAL,
                ram_pct REAL,
                disk_read_mb_s REAL,
                disk_write_mb_s REAL
            )
        """))

        # Indexes for common query patterns
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_hw_timestamp ON hardware_stats(timestamp)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_translations_created "
            "ON translations(created_at)"
        ))

        # Prune hardware_stats older than 24 hours
        await conn.execute(text(
            "DELETE FROM hardware_stats WHERE timestamp < datetime('now', '-24 hours')"
        ))

        # Indexes for EPUB query patterns
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_chapters_book_id ON chapters(book_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_paragraphs_chapter_id ON paragraphs(chapter_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_translations_source_text_id ON translations(source_text_id)"
        ))

        # Seed default settings (INSERT OR IGNORE preserves user changes)
        from .core.paths import EPUB_WATCH_DIR
        _epub_default = str(EPUB_WATCH_DIR).replace("\\", "/")
        await conn.execute(
            text(
                "INSERT OR IGNORE INTO settings (key, value) VALUES "
                "(:k1, :v1), (:k2, :v2)"
            ),
            {"k1": "epub_watch_folder", "v1": _epub_default,
             "k2": "auto_scan_interval", "v2": "60"},
        )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        yield session
