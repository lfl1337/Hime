import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Make scripts/ importable in tests
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import pytest
from app.database import init_db


@pytest.fixture(scope="session", autouse=True)
async def ensure_db_initialized():
    """Run inline migrations once before any test accesses the database."""
    await init_db()
