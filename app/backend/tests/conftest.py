"""Global pytest fixtures and configuration.

Test-DB isolation (P1-D1 fix):
    All tests run against an isolated temp SQLite DB. The production `hime.db`
    in the project root (and the CWD-adjacent `app/backend/hime.db` pollution
    location) is never touched by the test suite.

IMPORTANT — module import order:
    `HIME_DATA_DIR` MUST be set BEFORE any `app.config` / `app.database` import
    because `config.py` reads the env var at module top-level (not inside a
    function) and `database.py` binds its engine to `settings.db_url` at import
    time. If any consumer of `app.config` / `app.database` loads above the env
    setup block, the engine gets wired to the wrong path and the isolation is
    silently lost.

    Do NOT hoist the `from app.database import init_db` above the env setup.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Make the backend package importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Make scripts/ importable in tests (needed by training-related tests)
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ---- Test-DB isolation: MUST run BEFORE importing app.config / app.database ----
# We only override HIME_DATA_DIR. HIME_PROJECT_ROOT is intentionally left alone
# because test_paths.py / test_paths_v121.py call importlib.reload(paths) in an
# autouse fixture and expect the real project root to remain resolvable.
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="hime_pytest_"))
os.environ["HIME_DATA_DIR"] = str(_TEST_DATA_DIR)

import pytest  # noqa: E402

# Register all ORM models with Base.metadata BEFORE init_db() runs, so
# create_all() actually creates the tables the inline migrations then ALTER.
# Without this, an isolated test file that never touches models/routers/services
# hits "OperationalError: no such table: translations" during init_db().
import app.models  # noqa: F401, E402
from app.database import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def ensure_db_initialized():
    """Initialize the isolated test DB once per session, then tear it down."""
    # Defensive assertion: if something imported app.config above the env setup
    # block (e.g. an unwanted cached import), settings.db_url will not reference
    # our temp dir and we must fail loudly instead of silently polluting a real
    # database.
    from app.config import settings
    url = settings.db_url.replace("\\", "/")
    temp_posix = str(_TEST_DATA_DIR).replace("\\", "/")
    assert temp_posix in url, (
        f"Test DB URL {url} is not inside {temp_posix} — isolation leak! "
        "Something imported app.config before HIME_DATA_DIR was set."
    )

    await init_db()
    yield

    # Cleanup: remove the temp dir at session end. Windows sometimes holds
    # file handles open; ignore_errors keeps the session exit clean regardless.
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# Phase 8 — integration test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_client(monkeypatch):
    """FastAPI TestClient with HIME_DRY_RUN=1.

    HIME_DATA_DIR is already set to a temp dir by the module-level block above.
    We patch settings.hime_dry_run directly so runner_v2.py picks it up without
    requiring a module reload (which would break DB isolation).
    """
    from fastapi.testclient import TestClient
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "hime_dry_run", True)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_book_fixture() -> Path:
    """Return the path to tests/fixtures/sample_book.json."""
    return Path(__file__).resolve().parent / "fixtures" / "sample_book.json"


@pytest.fixture
async def db_session():
    """Function-scoped async SQLAlchemy session against the isolated test DB.

    Yields a session bound to the same temp SQLite that `ensure_db_initialized`
    created. The session is rolled back and closed on teardown so rows created
    by one test don't leak into another (best-effort — some tests commit).
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()
