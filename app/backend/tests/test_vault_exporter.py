"""Tests for incremental Obsidian vault exporter."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.rag.vault_exporter import sync_series, _chunk_filename


def _fake_store(chunks, last_update="2026-04-10"):
    store = MagicMock()
    store.all_chunks.return_value = chunks
    store.stats.return_value = {"chunk_count": len(chunks), "last_update": last_update}
    return store


CHUNKS_2 = [
    {"chunk_index": 0, "paragraph_id": 1, "book_id": 1, "chapter_id": 1,
     "source_text": "日本語テスト", "translated_text": "Japanese test"},
    {"chunk_index": 1, "paragraph_id": 2, "book_id": 1, "chapter_id": 1,
     "source_text": "第二文", "translated_text": "Second sentence"},
]


def test_chunk_filename_zero_padded():
    assert _chunk_filename(0) == "Chunk_0000.md"
    assert _chunk_filename(42) == "Chunk_0042.md"


def test_sync_writes_files(tmp_path: Path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "series_1.db").touch()

    with patch("app.rag.store.SeriesStore", return_value=_fake_store(CHUNKS_2)):
        result = sync_series(series_id=1, rag_dir=rag_dir, vault_dir=tmp_path)

    assert result["new_files"] == 2
    assert result["total_chunks"] == 2
    series_dir = tmp_path / "series_1"
    assert (series_dir / "Chunk_0000.md").exists()
    assert (series_dir / "Chunk_0001.md").exists()
    assert (series_dir / "_series_index.md").exists()
    assert (tmp_path / "_index.md").exists()


def test_chunk_file_has_wikilinks_and_flags(tmp_path: Path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "series_1.db").touch()

    with patch("app.rag.store.SeriesStore", return_value=_fake_store(CHUNKS_2)):
        sync_series(series_id=1, rag_dir=rag_dir, vault_dir=tmp_path)

    chunk0 = (tmp_path / "series_1" / "Chunk_0000.md").read_text(encoding="utf-8")
    assert "[[_series_index]]" in chunk0
    assert "[[Chunk_0001]]" in chunk0
    assert "series_id: 1" in chunk0


def test_incremental_skips_existing(tmp_path: Path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "series_1.db").touch()

    with patch("app.rag.store.SeriesStore", return_value=_fake_store(CHUNKS_2)):
        r1 = sync_series(series_id=1, rag_dir=rag_dir, vault_dir=tmp_path)
    with patch("app.rag.store.SeriesStore", return_value=_fake_store(CHUNKS_2)):
        r2 = sync_series(series_id=1, rag_dir=rag_dir, vault_dir=tmp_path)

    assert r1["new_files"] == 2
    assert r2["new_files"] == 0


def test_obsidian_graph_config_created(tmp_path: Path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "series_1.db").touch()

    with patch("app.rag.store.SeriesStore", return_value=_fake_store(CHUNKS_2)):
        sync_series(series_id=1, rag_dir=rag_dir, vault_dir=tmp_path)

    import json
    graph_json = tmp_path / ".obsidian" / "graph.json"
    assert graph_json.exists()
    data = json.loads(graph_json.read_text())
    assert "colorGroups" in data
    tags = [g["query"] for g in data["colorGroups"]]
    assert any("series-1" in t for t in tags)
