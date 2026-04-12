# scripts/vault_indexer/watcher.py
"""
watcher.py — Automatisches Re-Indexieren bei Vault-Änderungen.

Startet einen Watchdog-FileSystemEventHandler der auf .md-Änderungen reagiert.
Da vault_write Dateien programmatisch schreibt, sorgt der Watcher dafür dass
neue Notes sofort suchbar sind.

Usage:
    cd N:/Projekte/NiN/Hime
    python scripts/vault_indexer/watcher.py
    (läuft bis Ctrl+C)
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from chunker import file_to_chunks
from config import COLLECTION, EXCLUDE_DIRS, VAULT_PATH
from embedder import embed
from qdrant_ops import delete_file_chunks, ensure_collection, get_client, upsert_chunks


def _is_relevant(path: str) -> bool:
    p = Path(path)
    if p.suffix != ".md":
        return False
    return not any(part in EXCLUDE_DIRS for part in p.parts)


class VaultHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        self._client = get_client()

    def _reindex(self, src_path: str) -> None:
        path = Path(src_path)
        if not _is_relevant(src_path) or not path.exists():
            return
        rel = str(path.relative_to(VAULT_PATH))
        chunks = file_to_chunks(path, VAULT_PATH)
        if not chunks:
            return
        texts = [c.text for c in chunks]
        embeddings = asyncio.run(embed(texts))
        delete_file_chunks(self._client, rel)
        n = upsert_chunks(self._client, chunks, embeddings)
        print(f"[watcher] {rel}  -> {n} Chunk(s) indexiert")

    def _delete(self, src_path: str) -> None:
        if not _is_relevant(src_path):
            return
        rel = str(Path(src_path).relative_to(VAULT_PATH))
        delete_file_chunks(self._client, rel)
        print(f"[watcher] geloescht: {rel}")

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._reindex(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._reindex(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._delete(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._delete(event.src_path)
            self._reindex(event.dest_path)


def main() -> None:
    print(f"[watcher] Starte — ueberwache: {VAULT_PATH}")
    print(f"[watcher] Collection: {COLLECTION}  |  Ctrl+C zum Beenden\n")

    client = get_client()
    ensure_collection(client)

    observer = Observer()
    observer.schedule(VaultHandler(), str(VAULT_PATH), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    print("\n[watcher] Gestoppt.")


if __name__ == "__main__":
    main()
