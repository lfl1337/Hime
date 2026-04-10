"""
hime-rag MCP server — exposes Hime's per-series RAG index to Obsidian / Claude Desktop.

Run via stdio (registered in claude_desktop_config.json):
    "hime-rag": {
      "command": "uv",
      "args": ["--directory", "<path_to_hime>/app/backend", "run", "python", "-m", "mcp_server.hime_rag_mcp"],
      "env": {"HIME_RAG_DIR": "<path_to_hime>/data/rag"}
    }
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_log = logging.getLogger(__name__)

mcp = FastMCP("hime-rag")


def _resolve_rag_dir() -> Path:
    env = os.environ.get("HIME_RAG_DIR", "")
    if env:
        return Path(env)
    # Fallback: relative to this file → data/rag
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "rag"


def _get_store_stats(series_id: int) -> dict:
    from app.rag.store import SeriesStore
    db_path = _resolve_rag_dir() / f"series_{series_id}.db"
    if not db_path.exists():
        return {"chunk_count": 0, "last_update": None}
    store = SeriesStore(db_path)
    try:
        return store.stats()
    finally:
        store.close()


async def _rag_query_impl(series_id: int, text: str, top_k: int) -> list[dict]:
    from app.rag.retriever import retrieve_top_k
    db_path = _resolve_rag_dir() / f"series_{series_id}.db"
    if not db_path.exists():
        return []
    try:
        return await retrieve_top_k(series_id, text, top_k)
    except Exception as e:  # noqa: BLE001
        _log.warning("RAG query failed: %s", e)
        return []


async def _rag_stats_impl(series_id: int) -> dict:
    return _get_store_stats(series_id)


async def _rag_list_series_impl() -> list[dict]:
    rag_dir = _resolve_rag_dir()
    if not rag_dir.exists():
        return []
    result = []
    for db_file in sorted(rag_dir.glob("series_*.db")):
        try:
            sid = int(db_file.stem.split("_", 1)[1])
            stats = _get_store_stats(sid)
            result.append({"series_id": sid, **stats})
        except (ValueError, Exception):  # noqa: BLE001
            continue
    return result


@mcp.tool()
async def rag_query(series_id: int, text: str, top_k: int = 5) -> list[dict]:
    """Query the RAG index for a series. Returns top-k similar translation pairs."""
    return await _rag_query_impl(series_id=series_id, text=text, top_k=top_k)


@mcp.tool()
async def rag_stats(series_id: int) -> dict:
    """Return chunk count and last update timestamp for a series index."""
    return await _rag_stats_impl(series_id=series_id)


@mcp.tool()
async def rag_list_series() -> list[dict]:
    """List all indexed series with their chunk counts."""
    return await _rag_list_series_impl()


@mcp.tool()
async def rag_sync_vault(series_id: int | None = None) -> dict:
    """
    Sync Hime's RAG index into the dedicated Obsidian vault at obsidian-vault/.

    Incrementally adds new chunks only — existing files are not overwritten.
    If series_id is given, only that series is synced. If None, all indexed
    series are synced.

    After first sync, open obsidian-vault/ in Obsidian and switch to Graph View.
    """
    from app.rag.vault_exporter import sync_series
    from app.core import paths as _paths
    rag_dir = _resolve_rag_dir()
    vault_dir = _paths.OBSIDIAN_VAULT_DIR

    if series_id is not None:
        return sync_series(series_id=series_id, rag_dir=rag_dir, vault_dir=vault_dir)

    # Sync all series
    results = []
    for db_file in sorted(rag_dir.glob("series_*.db")):
        try:
            sid = int(db_file.stem.split("_", 1)[1])
            results.append(sync_series(series_id=sid, rag_dir=rag_dir, vault_dir=vault_dir))
        except (ValueError, Exception) as e:  # noqa: BLE001
            results.append({"series_id": None, "error": str(e)})
    total = sum(r.get("new_files", 0) for r in results)
    return {"synced_series": len(results), "total_new_files": total, "details": results}


@mcp.resource("rag://series/{series_id}/chunks")
async def rag_chunks_resource(series_id: int) -> str:
    """
    Full dump of a series index as markdown.
    Useful for Obsidian — returns all chunks as a browsable document.
    """
    from app.rag.store import SeriesStore
    db_path = _resolve_rag_dir() / f"series_{series_id}.db"
    if not db_path.exists():
        return f"# Series {series_id}\n\nNo index found."
    store = SeriesStore(db_path)
    try:
        chunks = store.all_chunks()
    finally:
        store.close()
    lines = [f"# Series {series_id} — RAG Index\n", f"**{len(chunks)} chunks**\n\n---\n"]
    for c in chunks:
        lines.append(f"## Chunk {c['chunk_index']} (paragraph {c['paragraph_id']})\n")
        lines.append(f"**JP:** {c['source_text']}\n\n")
        lines.append(f"**EN:** {c['translated_text']}\n\n---\n")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
