"""Integration tests for /api/v1/translations router.

Router: app/routers/translations.py
Prefix: /api/v1/translations
Endpoints tested:
  GET    /api/v1/translations/                — list → 200
  GET    /api/v1/translations/{id}            — get not-found → 404
  POST   /api/v1/translations/translate       — missing body → 422
  POST   /api/v1/translations/translate       — non-existent source_text_id → 404
  DELETE /api/v1/translations/{id}            — not-found → 404
"""


def test_list_translations_returns_200(test_client):
    """GET /api/v1/translations/ should return 200 and a list."""
    response = test_client.get("/api/v1/translations/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_translation_not_found(test_client):
    """GET /api/v1/translations/999999 should return 404."""
    response = test_client.get("/api/v1/translations/999999")
    assert response.status_code == 404


def test_create_translation_validation_error_empty_body(test_client):
    """POST /api/v1/translations/translate with empty body should return 422."""
    response = test_client.post("/api/v1/translations/translate", json={})
    assert response.status_code == 422


def test_create_translation_source_not_found(test_client):
    """POST /api/v1/translations/translate with non-existent source_text_id → 404."""
    payload = {"source_text_id": 999999}
    response = test_client.post("/api/v1/translations/translate", json=payload)
    assert response.status_code == 404


def test_delete_translation_not_found(test_client):
    """DELETE /api/v1/translations/999999 should return 404."""
    response = test_client.delete("/api/v1/translations/999999")
    assert response.status_code == 404
