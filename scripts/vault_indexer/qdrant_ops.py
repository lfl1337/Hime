# scripts/vault_indexer/qdrant_ops.py
"""Qdrant-Operationen: Collection anlegen, Chunks upserten, nach Datei löschen."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from config import COLLECTION, QDRANT_URL
from chunker import VaultChunk

VECTOR_DIM = 1024  # bge-m3


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: QdrantClient) -> None:
    """Legt die Collection an falls sie noch nicht existiert."""
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        print(f"[qdrant] Collection '{COLLECTION}' angelegt.")
    else:
        print(f"[qdrant] Collection '{COLLECTION}' existiert bereits.")


def _chunk_id(file_path: str, chunk_index: int) -> str:
    """Deterministischer Punkt-Hash aus Dateipfad + Chunk-Index."""
    raw = f"{file_path}::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


def upsert_chunks(
    client: QdrantClient,
    chunks: list[VaultChunk],
    embeddings: list[list[float]],
) -> int:
    """Fügt Chunks in Qdrant ein (upsert = update or insert). Gibt Anzahl zurück."""
    points = [
        PointStruct(
            id=_chunk_id(chunk.file_path, chunk.chunk_index),
            vector=embedding,
            payload={
                "file_path": chunk.file_path,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "title": chunk.title,
                "type": chunk.type,
                "project": chunk.project,
                "tags": chunk.tags,
            },
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]
    if points:
        client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def delete_file_chunks(client: QdrantClient, file_path: str) -> None:
    """Löscht alle Chunks einer Datei (beim Löschen/Umbenennen)."""
    client.delete(
        collection_name=COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
        ),
    )
