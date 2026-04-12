# scripts/shuukura_rag/phase_05_import.py
"""
Phase 5: 8 JP-Bände in Hime-DB importieren + RAG-Store befüllen.

Vorgehen:
  - Für jedes der 7 bilingualen Bände: Book + Chapter + Paragraph anlegen,
    Paragraph.source_text = JP, Paragraph.translated_text = EN-aligned,
    Paragraph.is_reviewed = True -> wird von build_for_book() indexiert
  - Für den 1 monolingualen Band: Book anlegen,
    Paragraph.is_reviewed = False -> NICHT indexiert
    (Begründung: ohne EN-Text würde JP als 'translated_text' im Prompt erscheinen)
  - Series-ID aus state.json (von Phase 0 bestimmt)
  - Direkte sqlite3-Writes (kein async FastAPI)
  - RAG-Indexierung via SeriesStore + embed_texts direkt

Idempotenz: Bücher mit gleichem file_path werden nicht doppelt angelegt.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows-Konsole: UTF-8 erzwingen
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import STAGING_DIR, ROOT, halt, load_state, save_state, write_report

# Backend-Pfad für SeriesStore + embed_texts
_BACKEND = ROOT / "app" / "backend"
sys.path.insert(0, str(_BACKEND))

from app.core.paths import RAG_DIR  # noqa: E402
from app.rag.embeddings import embed_texts  # noqa: E402
from app.rag.store import SeriesStore  # noqa: E402


def get_db(hime_db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(hime_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_or_create_book(
    conn: sqlite3.Connection, title: str, series_id: int, file_path: str, lang: str
) -> int:
    """Gibt book_id zurück. Legt Buch an falls noch nicht vorhanden."""
    row = conn.execute(
        "SELECT id FROM books WHERE file_path = ?", (file_path,)
    ).fetchone()
    if row:
        return row["id"]

    conn.execute(
        """
        INSERT INTO books (title, file_path, series_id, series_title, status,
                           total_chapters, total_paragraphs, translated_paragraphs,
                           imported_at)
        VALUES (?, ?, ?, ?, 'not_started', 0, 0, 0, ?)
        """,
        (title, file_path, series_id, "Shuukura",
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM books WHERE file_path = ?", (file_path,)
    ).fetchone()
    return row["id"]


def insert_chapters_and_paragraphs(
    conn: sqlite3.Connection,
    book_id: int,
    band_data: dict,
    aligned_pairs: list[dict] | None,  # None = monolingual
) -> int:
    """
    Legt Chapters + Paragraphs an. Gibt Anzahl eingefügter Paragraphen zurück.
    Idempotent: überspringt bereits vorhandene Chapters (by chapter_index).
    """
    is_bilingual = aligned_pairs is not None
    total_para = 0

    if is_bilingual:
        # Pairs nach chapter_idx gruppieren
        chapter_pairs: dict[int, list[dict]] = {}
        for p in aligned_pairs:
            ch = p.get("chapter_idx", 0)
            chapter_pairs.setdefault(ch, []).append(p)

        for ch_idx in sorted(chapter_pairs.keys()):
            pairs = chapter_pairs[ch_idx]
            chapter_title = f"Kapitel {ch_idx + 1}"
            if ch_idx < len(band_data["chapters"]):
                chapter_title = band_data["chapters"][ch_idx]["title"][:512]

            row = conn.execute(
                "SELECT id FROM chapters WHERE book_id = ? AND chapter_index = ?",
                (book_id, ch_idx)
            ).fetchone()
            if row:
                ch_id = row["id"]
            else:
                conn.execute(
                    """
                    INSERT INTO chapters (book_id, chapter_index, title, total_paragraphs,
                                         translated_paragraphs, status, is_front_matter)
                    VALUES (?, ?, ?, ?, 0, 'not_started', 0)
                    """,
                    (book_id, ch_idx, chapter_title, len(pairs)),
                )
                conn.commit()
                ch_id = conn.execute(
                    "SELECT id FROM chapters WHERE book_id = ? AND chapter_index = ?",
                    (book_id, ch_idx)
                ).fetchone()["id"]

            existing_count = conn.execute(
                "SELECT COUNT(*) FROM paragraphs WHERE chapter_id = ?", (ch_id,)
            ).fetchone()[0]
            if existing_count >= len(pairs):
                total_para += existing_count
                continue

            for para_idx, pair in enumerate(pairs):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO paragraphs
                        (chapter_id, paragraph_index, source_text, translated_text,
                         is_translated, is_skipped, is_reviewed, reviewed_at)
                    VALUES (?, ?, ?, ?, 1, 0, 1, ?)
                    """,
                    (ch_id, para_idx, pair["jp"], pair["en"],
                     datetime.now(timezone.utc).isoformat()),
                )
            conn.commit()
            total_para += len(pairs)
    else:
        # Monolingual — aus band_data, is_reviewed = False
        for ch_idx, ch_data in enumerate(band_data["chapters"]):
            row = conn.execute(
                "SELECT id FROM chapters WHERE book_id = ? AND chapter_index = ?",
                (book_id, ch_idx)
            ).fetchone()
            if row:
                ch_id = row["id"]
            else:
                conn.execute(
                    """
                    INSERT INTO chapters (book_id, chapter_index, title,
                                         total_paragraphs, translated_paragraphs, status, is_front_matter)
                    VALUES (?, ?, ?, ?, 0, 'not_started', 0)
                    """,
                    (book_id, ch_idx, ch_data["title"][:512], len(ch_data["paragraphs"])),
                )
                conn.commit()
                ch_id = conn.execute(
                    "SELECT id FROM chapters WHERE book_id = ? AND chapter_index = ?",
                    (book_id, ch_idx)
                ).fetchone()["id"]

            for para_idx, para in enumerate(ch_data["paragraphs"]):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO paragraphs
                        (chapter_id, paragraph_index, source_text, translated_text,
                         is_translated, is_skipped, is_reviewed)
                    VALUES (?, ?, ?, NULL, 0, 0, 0)
                    """,
                    (ch_id, para_idx, para["raw"]),
                )
            conn.commit()
            total_para += len(ch_data["paragraphs"])

    # Book-Stats aktualisieren
    n_chapters = conn.execute(
        "SELECT COUNT(*) FROM chapters WHERE book_id = ?", (book_id,)
    ).fetchone()[0]
    conn.execute(
        "UPDATE books SET total_paragraphs = ?, total_chapters = ? WHERE id = ?",
        (total_para, n_chapters, book_id),
    )
    conn.commit()
    return total_para


def index_book_in_rag(book_id: int, series_id: int, conn: sqlite3.Connection) -> int:
    """
    Indexiert ein Buch direkt in den SeriesStore.
    Liest Paragraphs mit is_reviewed=True aus der DB.
    """
    rows = conn.execute(
        """
        SELECT p.id, p.source_text, p.translated_text, p.paragraph_index,
               c.id as chapter_id
        FROM paragraphs p
        JOIN chapters c ON c.id = p.chapter_id
        WHERE c.book_id = ?
          AND p.is_reviewed = 1
          AND p.source_text != ''
          AND p.translated_text IS NOT NULL
          AND p.translated_text != ''
        ORDER BY p.paragraph_index
        """,
        (book_id,)
    ).fetchall()

    if not rows:
        return 0

    texts = [f"{r['source_text']}\n{r['translated_text']}" for r in rows]
    embeddings = embed_texts(texts)

    from app.rag.chunker import ChunkPair

    chunks = [
        ChunkPair(
            book_id=book_id,
            chapter_id=r["chapter_id"],
            paragraph_id=r["id"],
            source_text=r["source_text"],
            translated_text=r["translated_text"],
            chunk_index=r["paragraph_index"],
        )
        for r in rows
    ]

    db_path = RAG_DIR / f"series_{series_id}.db"
    store = SeriesStore(db_path)
    store.initialize()
    before = store.count()
    store.insert_chunks(chunks, embeddings)
    after = store.count()
    store.close()

    return after - before


def main() -> None:
    print("\n=== Phase 5: DB-Import + RAG-Indexierung ===\n")
    state = load_state()

    hime_db   = state.get("hime_db")
    series_id = state.get("series_id")
    matched_pairs = state.get("matched_pairs", [])
    mono_jp_bands = state.get("mono_jp_bands", [])

    if not hime_db or not series_id:
        halt("hime_db oder series_id fehlt in state.json — Phase 0 ausführen.")
    if not matched_pairs:
        halt("matched_pairs fehlt — Phase 3 ausführen.")

    aligned_files = {
        int(Path(f).stem.split("_")[-1]): f
        for f in state.get("aligned_files", [])
    }
    if not aligned_files:
        halt("aligned_files fehlt — Phase 4 ausführen.")

    conn = get_db(hime_db)
    import_stats: list[dict] = []
    rag_stats: list[dict] = []

    # --- Bilinguale Bände ---
    print("-- Bilinguale Baende --")
    for pair in matched_pairs:
        band_nr = pair["jp_band"]
        jp_data = json.loads(Path(pair["jp_file"]).read_text(encoding="utf-8"))
        aligned_file = aligned_files.get(band_nr)
        if not aligned_file:
            print(f"  Band {band_nr:02d}: kein aligned_file — übersprungen.")
            continue

        aligned_pairs_data = [
            json.loads(line)
            for line in Path(aligned_file).read_text(encoding="utf-8").strip().splitlines()
        ]

        title = f"Shuukura Band {band_nr:02d} (JP/EN)"
        book_id = get_or_create_book(
            conn, title, series_id, pair["jp_file"], lang="ja"
        )
        print(f"  Band {band_nr:02d}: book_id={book_id}", end=" ", flush=True)

        n_para = insert_chapters_and_paragraphs(conn, book_id, jp_data, aligned_pairs_data)
        print(f"-> {n_para} Paragraphen", end=" ", flush=True)

        n_rag = index_book_in_rag(book_id, series_id, conn)
        print(f"-> +{n_rag} RAG-Chunks")

        import_stats.append({"band": band_nr, "book_id": book_id, "paragraphs": n_para})
        rag_stats.append({"band": band_nr, "new_chunks": n_rag})

    # --- Monolingualer Band ---
    print("\n-- Monolingualer Band (is_reviewed=False, kein RAG) --")
    for mono in mono_jp_bands:
        band_nr = mono["jp_band"]
        jp_data = json.loads(Path(mono["jp_file"]).read_text(encoding="utf-8"))
        title = f"Shuukura Band {band_nr:02d} (JP only)"
        book_id = get_or_create_book(
            conn, title, series_id, mono["jp_file"], lang="ja"
        )
        print(f"  Band {band_nr:02d}: book_id={book_id}", end=" ", flush=True)

        n_para = insert_chapters_and_paragraphs(conn, book_id, jp_data, aligned_pairs=None)
        print(f"-> {n_para} Paragraphen (nicht indexiert)")

        import_stats.append({"band": band_nr, "book_id": book_id,
                              "paragraphs": n_para, "mono": True})

    conn.close()

    # Selbst-Test: RAG-Chunk-Zählung
    db_path = RAG_DIR / f"series_{series_id}.db"
    store = SeriesStore(db_path)
    store.initialize()
    total_chunks = store.count()
    store.close()
    print(f"\nRAG-DB series_{series_id}.db: {total_chunks} Chunks total")

    save_state({
        "import_stats": import_stats,
        "rag_stats": rag_stats,
        "total_rag_chunks": total_chunks,
    })

    report_rows = "\n".join(
        f"| {s['band']:02d} | {s.get('book_id','?')} | {s['paragraphs']} "
        f"| {'—' if s.get('mono') else next((r['new_chunks'] for r in rag_stats if r['band']==s['band']), 0)} "
        f"| {'JP only (nicht indexiert)' if s.get('mono') else 'bilingual'} |"
        for s in import_stats
    )

    write_report("05_rag_indexing.md", f"""# Phase 5: DB-Import + RAG-Indexierung

## Ergebnis

| Band | Book-ID | Paragraphen | RAG +Chunks | Art |
|---|---|---|---|---|
{report_rows}

**Gesamt RAG-Chunks in series_{series_id}.db: {total_chunks}**

## DB-Pfad
`{hime_db}`

## RAG-DB
`{db_path}`

## Hinweis Monolingualer Band
Band {[m['jp_band'] for m in mono_jp_bands]} wurde **nicht** indexiert (kein EN-Pendant).
`is_reviewed=False` verhindert, dass JP-Text faelschlicherweise als Uebersetzung erscheint.
""")
    print("\n[OK] Phase 5 abgeschlossen.")


if __name__ == "__main__":
    main()
