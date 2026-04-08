"""Tests for v1.2.1 path additions: EMBEDDINGS_DIR, RAG_DIR."""
from pathlib import Path

from app.core import paths


def test_embeddings_dir_exists():
    assert hasattr(paths, "EMBEDDINGS_DIR")
    assert isinstance(paths.EMBEDDINGS_DIR, Path)


def test_rag_dir_exists():
    assert hasattr(paths, "RAG_DIR")
    assert isinstance(paths.RAG_DIR, Path)


def test_embeddings_dir_under_models_by_default(monkeypatch):
    # When HIME_EMBEDDINGS_DIR is unset, default = MODELS_DIR / "embeddings"
    monkeypatch.delenv("HIME_EMBEDDINGS_DIR", raising=False)
    # Re-import to get fresh module values
    import importlib
    importlib.reload(paths)
    assert paths.EMBEDDINGS_DIR.name == "embeddings"


def test_rag_dir_under_data_by_default(monkeypatch):
    monkeypatch.delenv("HIME_RAG_DIR", raising=False)
    import importlib
    importlib.reload(paths)
    assert paths.RAG_DIR.name == "rag"


def test_embeddings_dir_overridable(monkeypatch, tmp_path):
    monkeypatch.setenv("HIME_EMBEDDINGS_DIR", str(tmp_path / "custom_emb"))
    import importlib
    importlib.reload(paths)
    assert paths.EMBEDDINGS_DIR == tmp_path / "custom_emb"
