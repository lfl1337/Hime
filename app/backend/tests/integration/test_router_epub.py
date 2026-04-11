"""Integration tests for /api/v1/epub router.

Router: app/routers/epub.py
Prefix: /api/v1/epub
Endpoints tested:
  GET /api/v1/epub/books                   — list → 200 + list
  GET /api/v1/epub/export/{chapter_id}     — non-existent chapter → 200 with empty content
                                             (export_chapter returns "" for unknown chapter_id,
                                              no 404 is raised by the service)
"""


def test_list_books_empty(test_client):
    """GET /api/v1/epub/books should return 200 and a list (may be empty)."""
    response = test_client.get("/api/v1/epub/books")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_export_chapter_unknown_id_returns_empty_content(test_client):
    """GET /api/v1/epub/export/999999 returns 200 with empty content string.

    Note: export_chapter() does not raise 404 for unknown chapter_id; it just
    returns an empty join of an empty paragraphs list. The router returns 200.
    """
    response = test_client.get("/api/v1/epub/export/999999")
    assert response.status_code == 200
    body = response.json()
    assert "content" in body
    assert body["content"] == ""
