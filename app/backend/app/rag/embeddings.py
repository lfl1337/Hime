"""
bge-m3 embeddings wrapper.

Lazy-loads the model from `${HIME_EMBEDDINGS_DIR}/bge-m3`. If the model is not
present locally, the wrapper raises a clear error unless `HIME_ALLOW_DOWNLOADS=true`,
in which case `sentence-transformers` will download it (~1.3GB).

CRITICAL: This is the ONLY model in the project allowed to be downloaded
automatically when the user has confirmed disk space.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from ..config import settings
from ..core import paths as _paths

_log = logging.getLogger(__name__)

_MODEL = None


def _resolve_embeddings_dir() -> Path:
    if settings.hime_embeddings_dir:
        return Path(settings.hime_embeddings_dir)
    return _paths.EMBEDDINGS_DIR


def get_model():
    """Return the SentenceTransformer model, loading it on first call."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    embeddings_dir = _resolve_embeddings_dir()
    bge_path = embeddings_dir / "bge-m3"

    from sentence_transformers import SentenceTransformer

    if bge_path.exists():
        _log.info("[bge-m3] Loading from %s", bge_path)
        _MODEL = SentenceTransformer(str(bge_path))
        return _MODEL

    if not settings.hime_allow_downloads:
        raise RuntimeError(
            f"bge-m3 model not found at {bge_path} and HIME_ALLOW_DOWNLOADS is false. "
            "Set HIME_ALLOW_DOWNLOADS=true after confirming you have ~1.3GB of disk space."
        )

    _log.warning("[bge-m3] Downloading ~1.3GB model from HuggingFace into %s", bge_path)
    bge_path.parent.mkdir(parents=True, exist_ok=True)
    _MODEL = SentenceTransformer("BAAI/bge-m3", cache_folder=str(bge_path.parent))
    return _MODEL


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    model = get_model()
    arr = model.encode(list(texts), normalize_embeddings=True)
    return [list(map(float, row)) for row in arr]


def embedding_dim() -> int:
    return 1024  # bge-m3 fixed
