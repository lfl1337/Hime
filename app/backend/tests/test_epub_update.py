import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import AsyncSessionLocal
from app.models import Book


@pytest.fixture
async def sample_book(tmp_path):
    async with AsyncSessionLocal() as session:
        book = Book(
            title="Test Book",
            file_path=str(tmp_path / "test.epub"),
            total_chapters=0,
            total_paragraphs=0,
        )
        session.add(book)
        await session.commit()
        await session.refresh(book)
        book_id = book.id
    yield book_id
    async with AsyncSessionLocal() as session:
        b = await session.get(Book, book_id)
        if b:
            await session.delete(b)
            await session.commit()


@pytest.mark.asyncio
async def test_patch_book_series_persists(sample_book):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/epub/books/{sample_book}",
            json={"series_id": 42, "series_title": "Bloom into You"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["series_id"] == 42
    assert data["series_title"] == "Bloom into You"


@pytest.mark.asyncio
async def test_patch_book_series_clears_with_null(sample_book):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/api/v1/epub/books/{sample_book}",
            json={"series_id": 1, "series_title": "Some Series"},
        )
        resp = await client.patch(
            f"/api/v1/epub/books/{sample_book}",
            json={"series_id": None, "series_title": None},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["series_id"] is None
    assert data["series_title"] is None


@pytest.mark.asyncio
async def test_patch_book_404_for_missing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/v1/epub/books/999999",
            json={"series_id": 1, "series_title": "x"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_library_includes_series_fields(sample_book):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/epub/books")
    assert resp.status_code == 200
    books = resp.json()
    book = next((b for b in books if b["id"] == sample_book), None)
    assert book is not None
    assert "series_id" in book
    assert "series_title" in book
