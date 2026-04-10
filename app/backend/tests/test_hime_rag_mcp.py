"""Tests for hime-rag MCP server tool functions."""
from unittest.mock import patch

import pytest

from mcp_server.hime_rag_mcp import _rag_query_impl, _rag_stats_impl, _rag_list_series_impl


@pytest.mark.asyncio
async def test_rag_query_returns_chunks():
    fake_chunks = [
        {"paragraph_id": 1, "source_text": "JP1", "translated_text": "EN1", "score": 0.95}
    ]
    with patch("app.rag.retriever.retrieve_top_k", return_value=fake_chunks), \
         patch("mcp_server.hime_rag_mcp._resolve_rag_dir") as mock_dir:
        # Fake a db file existing so the function doesn't bail early
        import tempfile, pathlib
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "series_1.db").touch()
        mock_dir.return_value = tmp
        result = await _rag_query_impl(series_id=1, text="猫", top_k=5)
    assert len(result) == 1
    assert result[0]["source_text"] == "JP1"


@pytest.mark.asyncio
async def test_rag_stats_returns_dict():
    with patch("mcp_server.hime_rag_mcp._get_store_stats", return_value={"chunk_count": 42, "last_update": "2026-04-10"}):
        result = await _rag_stats_impl(series_id=1)
    assert result["chunk_count"] == 42


@pytest.mark.asyncio
async def test_rag_list_series_empty_when_no_dbs(tmp_path):
    with patch("mcp_server.hime_rag_mcp._resolve_rag_dir", return_value=tmp_path):
        result = await _rag_list_series_impl()
    assert result == []


@pytest.mark.asyncio
async def test_rag_query_graceful_on_missing_series(tmp_path):
    with patch("mcp_server.hime_rag_mcp._resolve_rag_dir", return_value=tmp_path):
        result = await _rag_query_impl(series_id=999, text="test", top_k=5)
    assert result == []
