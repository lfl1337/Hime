"""
Per-series sqlite-vec store.

One sqlite database per series, kept under ${HIME_RAG_DIR}/series_{id}.db.
Uses the `sqlite-vec` extension for the vec0 virtual table.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from .chunker import ChunkPair

_log = logging.getLogger(__name__)


def _open_with_vec(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


class SeriesStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _get(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = _open_with_vec(self.db_path)
        return self._conn

    def initialize(self) -> None:
        conn = self._get()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                book_id INTEGER,
                chapter_id INTEGER,
                paragraph_id INTEGER UNIQUE,
                source_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                chunk_index INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[1024]
            )
        """)
        conn.commit()

    def insert_chunks(
        self,
        chunks: list[ChunkPair],
        embeddings: list[list[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have same length")
        conn = self._get()
        for chunk, vec in zip(chunks, embeddings, strict=False):
            cur = conn.execute(
                "SELECT id FROM chunks WHERE paragraph_id = ?", (chunk.paragraph_id,)
            )
            if cur.fetchone():
                continue
            cur = conn.execute(
                """
                INSERT INTO chunks (book_id, chapter_id, paragraph_id, source_text, translated_text, chunk_index)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chunk.book_id, chunk.chapter_id, chunk.paragraph_id,
                 chunk.source_text, chunk.translated_text, chunk.chunk_index),
            )
            chunk_id = cur.lastrowid
            conn.execute(
                "INSERT INTO chunk_vectors (chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, json.dumps(vec)),
            )
        conn.commit()

    def query(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        conn = self._get()
        # P2-F2 fix: sqlite-vec 0.1.9+ requires `AND k = ?` on vec0 virtual-table
        # knn queries — `LIMIT ?` alone raises "A LIMIT or 'k = ?' constraint is
        # required on vec0 knn queries". Binding k explicitly is the documented
        # shape (see https://alexgarcia.xyz/sqlite-vec/api-reference.html#knn).
        rows = conn.execute(
            """
            SELECT c.book_id, c.chapter_id, c.paragraph_id, c.source_text, c.translated_text, v.distance
            FROM chunk_vectors v
            JOIN chunks c ON c.id = v.chunk_id
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (json.dumps(query_embedding), top_k),
        ).fetchall()
        return [
            {
                "book_id": r[0], "chapter_id": r[1], "paragraph_id": r[2],
                "source_text": r[3], "translated_text": r[4], "distance": r[5],
            }
            for r in rows
        ]

    def count(self) -> int:
        conn = self._get()
        return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def stats(self) -> dict:
        conn = self._get()
        count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        last = conn.execute("SELECT MAX(created_at) FROM chunks").fetchone()[0]
        return {"chunk_count": count, "last_update": last}

    def all_chunks(self) -> list[dict]:
        """Return all stored chunks as plain dicts (for Obsidian vault export)."""
        conn = self._get()
        rows = conn.execute(
            "SELECT chunk_index, paragraph_id, book_id, chapter_id, source_text, translated_text "
            "FROM chunks ORDER BY chunk_index"
        ).fetchall()
        return [
            {
                "chunk_index": r[0], "paragraph_id": r[1],
                "book_id": r[2], "chapter_id": r[3],
                "source_text": r[4], "translated_text": r[5],
            }
            for r in rows
        ]

    def wipe(self) -> None:
        if self.db_path.exists():
            self.close()
            self.db_path.unlink()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
