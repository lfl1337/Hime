"""RAG endpoints — index, query, stats, delete, vault sync."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.paths import RAG_DIR
from ..database import get_session
from ..models import Book
from ..rag.indexer import build_for_book
from ..rag.retriever import retrieve_top_k
from ..rag.store import SeriesStore

router = APIRouter(prefix="/rag", tags=["rag"])


class IndexResponse(BaseModel):
    book_id: int
    new_chunks: int


@router.post("/index/{book_id}", response_model=IndexResponse)
async def index_book(
    book_id: int,
    session: AsyncSession = Depends(get_session),
) -> IndexResponse:
    book = await session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.series_id is None:
        raise HTTPException(status_code=400, detail="Book has no series_id; set one before indexing")
    new_chunks = await build_for_book(book_id)
    return IndexResponse(book_id=book_id, new_chunks=new_chunks)


class QueryRequest(BaseModel):
    series_id: int
    text: str = Field(..., max_length=10_000)
    top_k: int = Field(default=5, ge=1, le=20)


class QueryResponse(BaseModel):
    chunks: list[dict]


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest) -> QueryResponse:
    # W5: Backend-only/CLI — no frontend caller as of v1.1.2; planned for RAG panel
    chunks = await retrieve_top_k(body.series_id, body.text, body.top_k)
    return QueryResponse(chunks=chunks)


class SeriesStats(BaseModel):
    series_id: int
    chunk_count: int
    last_update: str | None


@router.get("/series/{series_id}/stats", response_model=SeriesStats)
async def stats(series_id: int) -> SeriesStats:
    db_path = RAG_DIR / f"series_{series_id}.db"  # series_id is int — no path traversal possible
    if not db_path.exists():
        return SeriesStats(series_id=series_id, chunk_count=0, last_update=None)
    store = SeriesStore(db_path)
    try:
        s = store.stats()
        return SeriesStats(series_id=series_id, chunk_count=s["chunk_count"], last_update=s["last_update"])
    finally:
        store.close()


@router.delete("/series/{series_id}")
async def delete_series_index(series_id: int) -> dict:
    db_path = RAG_DIR / f"series_{series_id}.db"  # series_id is int — no path traversal possible
    if not db_path.exists():
        return {"deleted": False, "reason": "not found"}
    store = SeriesStore(db_path)
    store.wipe()
    return {"deleted": True}


class VaultSyncResponse(BaseModel):
    series_id: int | None
    new_files: int
    total_chunks: int | None = None


@router.post("/vault/sync", response_model=list[VaultSyncResponse])
async def vault_sync(series_id: int | None = None) -> list[VaultSyncResponse]:
    """Sync RAG index into obsidian-vault/. Incremental — only new chunks written.

    W5: Backend-only/CLI — no frontend caller as of v1.1.2; planned for settings panel.
    """
    from ..rag.vault_exporter import sync_series

    if series_id is not None:
        result = sync_series(series_id=series_id)
        return [VaultSyncResponse(
            series_id=result.get("series_id"),
            new_files=result.get("new_files", 0),
            total_chunks=result.get("total_chunks"),
        )]

    results = []
    for db_file in sorted(RAG_DIR.glob("series_*.db")):
        try:
            sid = int(db_file.stem.split("_", 1)[1])
            r = sync_series(series_id=sid)
            results.append(VaultSyncResponse(
                series_id=r.get("series_id"),
                new_files=r.get("new_files", 0),
                total_chunks=r.get("total_chunks"),
            ))
        except (ValueError, Exception):  # noqa: BLE001
            continue
    return results
