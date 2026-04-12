# scripts/vault_indexer/embedder.py
"""Erzeugt Embeddings via Ollama (bge-m3, läuft lokal)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx

from config import EMBED_MODEL, OLLAMA_BASE


async def embed(texts: list[str]) -> list[list[float]]:
    """Embedded eine Liste von Texten. Gibt Vektoren in gleicher Reihenfolge zurück."""
    results: list[list[float]] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for text in texts:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
            )
            resp.raise_for_status()
            data = resp.json()
            if "embedding" not in data:
                raise ValueError(f"Ollama response missing 'embedding': {list(data.keys())}")
            results.append(data["embedding"])
    return results
