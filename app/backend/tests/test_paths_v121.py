"""Tests for v1.2.1 path additions: EMBEDDINGS_DIR, RAG_DIR."""
import importlib
from pathlib import Path

import pytest

from app.core import paths


@pytest.fixture(autouse=True)
def _reset_paths_module():
    """Restore the paths module to its pristine state after each test.

    Several tests in this file mutate env vars and call importlib.reload(paths).
    monkeypatch restores env vars but doesn't re-reload the module, so without
    this fixture later tests in the same session would see stale state.
    """
    yield
    importlib.reload(paths)


def test_embeddings_dir_exists():
    assert hasattr(paths, "EMBEDDINGS_DIR")
    assert isinstance(paths.EMBEDDINGS_DIR, Path)


def test_rag_dir_exists():
    assert hasattr(paths, "RAG_DIR")
    assert isinstance(paths.RAG_DIR, Path)


def test_embeddings_dir_under_models_by_default(monkeypatch):
    # When HIME_EMBEDDINGS_DIR is unset, default = MODELS_DIR / "embeddings"
    monkeypatch.delenv("HIME_EMBEDDINGS_DIR", raising=False)
    importlib.reload(paths)
    assert paths.EMBEDDINGS_DIR.name == "embeddings"
    assert paths.EMBEDDINGS_DIR.parent == paths.MODELS_DIR


def test_rag_dir_under_data_by_default(monkeypatch):
    monkeypatch.delenv("HIME_RAG_DIR", raising=False)
    importlib.reload(paths)
    assert paths.RAG_DIR.name == "rag"
    assert paths.RAG_DIR.parent == paths.DATA_DIR


def test_embeddings_dir_overridable(monkeypatch, tmp_path):
    monkeypatch.setenv("HIME_EMBEDDINGS_DIR", str(tmp_path / "custom_emb"))
    importlib.reload(paths)
    assert paths.EMBEDDINGS_DIR == tmp_path / "custom_emb"


def test_rag_dir_overridable(monkeypatch, tmp_path):
    monkeypatch.setenv("HIME_RAG_DIR", str(tmp_path / "custom_rag"))
    importlib.reload(paths)
    assert paths.RAG_DIR == tmp_path / "custom_rag"
