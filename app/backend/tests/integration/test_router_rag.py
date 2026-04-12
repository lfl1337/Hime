"""Integration tests for /api/v1/rag router.

Router: app/routers/rag.py
Prefix: /api/v1/rag
Endpoints tested:
  POST /api/v1/rag/query                       — endpoint exists (any non-404)
  GET  /api/v1/rag/series/{series_id}/stats    — returns 200 with empty stats for unknown series
"""


def test_rag_query_endpoint_exists(test_client):
    """POST /api/v1/rag/query should not return 404 (endpoint is registered)."""
    payload = {"series_id": 1, "text": "テストクエリ", "top_k": 3}
    response = test_client.post("/api/v1/rag/query", json=payload)
    # The endpoint exists; it may fail internally (e.g. no bge-m3 model) but must not 404.
    assert response.status_code != 404, (
        f"Expected endpoint to exist, got 404. Body: {response.text}"
    )


def test_rag_series_stats_unknown_series(test_client):
    """GET /api/v1/rag/series/999999/stats returns 200 with chunk_count=0 for unknown series."""
    response = test_client.get("/api/v1/rag/series/999999/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["series_id"] == 999999
    assert body["chunk_count"] == 0
    assert body["last_update"] is None
