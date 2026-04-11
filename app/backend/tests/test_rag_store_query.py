"""Regression test for P2-F2: rag.store.SeriesStore.query() must not crash on knn search.

Uses the real `data/rag/series_1.db` populated during Phase 2 with 8 chunks of
real bge-m3 embeddings (1024-dim). Does NOT load the bge-m3 model — a random
1024-dim unit vector is enough to exercise the SQL path, which is what this
regression is about.

The pre-existing bug: store.query() used
    WHERE v.embedding MATCH ? ORDER BY v.distance LIMIT ?
which raises `sqlite3.OperationalError` on sqlite-vec 0.1.9+ virtual tables.
The correct shape is
    WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance
with `k = ?` binding the top-k count instead of LIMIT.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import app.models  # noqa: F401 — register ORM tables on Base.metadata

# data/rag/series_1.db lives at <project_root>/data/rag/series_1.db
# tests/test_*.py lives at <project_root>/app/backend/tests/
# So: parents[0]=tests, [1]=backend, [2]=app, [3]=project_root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERIES_1_DB = PROJECT_ROOT / "data" / "rag" / "series_1.db"


def _query_vec():
    """Build a 1024-dim unit-norm random vector as a Python list (not numpy).

    store.query() passes the embedding through json.dumps, which can't serialize
    numpy arrays. Using a pure-Python list avoids that trap.
    """
    import random
    rng = random.Random(42)
    raw = [rng.gauss(0.0, 1.0) for _ in range(1024)]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / (norm + 1e-12) for x in raw]


def test_series_1_db_exists():
    """Sanity: the Phase 2 populated DB must still exist."""
    assert SERIES_1_DB.exists(), (
        f"Missing: {SERIES_1_DB} — was Phase 2 re-index undone?"
    )


def test_series_1_db_has_chunks():
    """Sanity: the Phase 2 populated DB must have its 8 chunks."""
    if not SERIES_1_DB.exists():
        pytest.skip("series_1.db not present")
    from app.rag import store
    s = store.SeriesStore(SERIES_1_DB)
    try:
        count = s.count()
    finally:
        s.close()
    assert count >= 1, f"Expected at least 1 chunk in series_1.db, got {count}"


def test_rag_store_query_returns_results():
    """query() must not raise and must return top_k results from the populated DB."""
    if not SERIES_1_DB.exists():
        pytest.skip("series_1.db not present")
    from app.rag import store
    query_vec = _query_vec()
    assert len(query_vec) == 1024

    s = store.SeriesStore(SERIES_1_DB)
    try:
        results = s.query(query_embedding=query_vec, top_k=3)
    finally:
        s.close()

    # Up-to-top_k results. Must be > 0 given the DB has >= 1 chunk.
    assert len(results) > 0, "Expected at least 1 result from a populated store"
    assert len(results) <= 3, f"Expected at most 3 results, got {len(results)}"

    # Each result dict must carry the expected keys.
    for r in results:
        assert isinstance(r, dict), f"Unexpected result shape: {r!r}"
        for k in ("book_id", "chapter_id", "paragraph_id", "source_text",
                  "translated_text", "distance"):
            assert k in r, f"Missing key {k!r} in result {r!r}"
        assert isinstance(r["distance"], (int, float))
