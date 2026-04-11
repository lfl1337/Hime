"""Regression test for P1-D1: test suite must not touch the production hime.db.

The previous conftest.py imported `init_db` at module top-level without first
setting `HIME_DATA_DIR`, so `settings.db_url` resolved to the CWD-relative
`./hime.db` (or, when pytest ran from `app/backend/`, to
`app/backend/hime.db` — still production-adjacent). Every pytest run mutated
production-side state: a fresh hime.db was created, tables were initialized,
indexes were built, and default settings were seeded on each session.

After the Pass B Task 3.7 fix, `conftest.py` must set `HIME_DATA_DIR` to an
isolated temp dir BEFORE importing `app.config` / `app.database`, so the
engine is bound to the temp DB.
"""
import hashlib
from pathlib import Path

import pytest

import app.models  # noqa: F401 — register ORM tables on Base.metadata


def test_conftest_uses_isolated_test_db():
    """`settings.db_url` must NOT point at the production DB after the fix."""
    from app.config import settings
    url = settings.db_url.replace("\\", "/")
    # CWD-relative fallback from the pre-fix conftest:
    assert "./hime.db" not in url, (
        f"Test DB URL still uses CWD-relative fallback: {url}"
    )
    # Absolute-path pollution: must not reference the project root hime.db
    project_root = Path(__file__).resolve().parents[3]
    prod_db_fragment = (project_root / "hime.db").as_posix()
    assert prod_db_fragment not in url, (
        f"Test DB URL points at root production hime.db: {url}"
    )
    backend_db_fragment = (project_root / "app" / "backend" / "hime.db").as_posix()
    assert backend_db_fragment not in url, (
        f"Test DB URL points at app/backend/hime.db (pollution location): {url}"
    )
    # Must live in an isolated hime_pytest_ temp dir.
    url_lower = url.lower()
    assert "hime_pytest_" in url_lower, (
        f"Test DB URL must be in a hime_pytest_ temp dir (conftest isolation); got: {url}"
    )


def test_production_db_header_unchanged_by_this_test_run():
    """Running a small query via AsyncSessionLocal must not touch production hime.db."""
    import asyncio

    from sqlalchemy import text

    project_root = Path(__file__).resolve().parents[3]
    prod_db = project_root / "hime.db"
    if not prod_db.exists():
        pytest.skip("Production hime.db not present — nothing to protect")

    before = hashlib.sha256(prod_db.read_bytes()[:4096]).hexdigest()

    from app.database import AsyncSessionLocal

    async def _probe():
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))

    asyncio.run(_probe())

    after = hashlib.sha256(prod_db.read_bytes()[:4096]).hexdigest()
    assert before == after, (
        "Production hime.db header changed during this test run — isolation leak! "
        f"before={before[:16]} after={after[:16]}"
    )


def test_backend_dir_hime_db_not_created():
    """No `hime.db` file must be created beside app/backend/ during a test run."""
    backend_dir = Path(__file__).resolve().parents[1]
    backend_hime = backend_dir / "hime.db"
    assert not backend_hime.exists(), (
        f"Pollution file present at {backend_hime}. The conftest is leaking "
        "the test DB into the backend directory. This file was likely created "
        "before the isolation fix landed — archive it and re-run."
    )
