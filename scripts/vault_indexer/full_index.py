# scripts/vault_indexer/full_index.py
"""
full_index.py — Vollständiger Index-Aufbau (run once oder zum Rebuild).

Usage:
    cd N:/Projekte/NiN/Hime
    python scripts/vault_indexer/full_index.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from chunker import file_to_chunks
from config import COLLECTION, EXCLUDE_DIRS, VAULT_PATH
from embedder import embed
from qdrant_ops import delete_file_chunks, ensure_collection, get_client, upsert_chunks


def collect_md_files(vault: Path) -> list[Path]:
    return [
        p for p in vault.rglob("*.md")
        if not any(part in EXCLUDE_DIRS for part in p.parts)
    ]


async def index_file(client, vault: Path, path: Path) -> int:
    rel = str(path.relative_to(vault))
    chunks = file_to_chunks(path, vault)
    if not chunks:
        return 0
    texts = [c.text for c in chunks]
    embeddings = await embed(texts)
    delete_file_chunks(client, rel)
    return upsert_chunks(client, chunks, embeddings)


async def main() -> None:
    print(f"[full_index] Vault: {VAULT_PATH}")
    print(f"[full_index] Collection: {COLLECTION}")

    client = get_client()
    ensure_collection(client)

    files = collect_md_files(VAULT_PATH)
    print(f"[full_index] {len(files)} .md-Datei(en) gefunden")

    if not files:
        print("[full_index] Vault ist leer — nichts zu indexieren.")
        return

    total = 0
    for i, path in enumerate(files, 1):
        n = await index_file(client, VAULT_PATH, path)
        rel = path.relative_to(VAULT_PATH)
        print(f"  [{i}/{len(files)}] {rel}  -> {n} Chunk(s)")
        total += n

    print(f"\n[OK] {total} Chunks in '{COLLECTION}' indexiert.")


if __name__ == "__main__":
    asyncio.run(main())
