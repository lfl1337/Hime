"""Integration tests for /api/v1/texts router.

Router: app/routers/texts.py
Prefix: /api/v1/texts
Endpoints tested:
  GET  /api/v1/texts/              — list (may be empty)
  GET  /api/v1/texts/{text_id}     — get not-found → 404
  POST /api/v1/texts/              — create → 201
  POST /api/v1/texts/              — missing required fields → 422
"""


def test_list_texts_returns_200(test_client):
    """GET /api/v1/texts/ should return 200 and a list (possibly empty)."""
    response = test_client.get("/api/v1/texts/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_text_not_found(test_client):
    """GET /api/v1/texts/999999 should return 404."""
    response = test_client.get("/api/v1/texts/999999")
    assert response.status_code == 404


def test_create_text_returns_201(test_client):
    """POST /api/v1/texts/ with valid payload should return 201 and the created text."""
    payload = {
        "title": "統合テスト用タイトル",
        "content": "これは統合テスト用のコンテンツです。",
        "language": "ja",
    }
    response = test_client.post("/api/v1/texts/", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == payload["title"]
    assert body["content"] == payload["content"]
    assert body["language"] == "ja"
    assert "id" in body


def test_create_text_validation_error(test_client):
    """POST /api/v1/texts/ with missing required fields should return 422."""
    response = test_client.post("/api/v1/texts/", json={})
    assert response.status_code == 422
