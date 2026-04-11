"""
Re-index series 1 and 2 RAG stores by reading existing vault markdown files.

Background: the production hime.db has 21 books but all have series_id=None,
and 80 313 paragraphs with zero `is_reviewed=True`. Therefore the standard
`build_for_book()` path (which requires books with series_id AND reviewed
paragraphs) cannot run. This fallback script bypasses that constraint by
reading the existing Obsidian vault chunks (8 in series_1, 6 in series_2) and
calling the same SeriesStore + embed_texts primitives directly — exercising
real bge-m3 inference against the downloaded local model.

Run this BEFORE the backend smoke-test. Both env vars must be set so the
embedding wrapper and path resolver find the right directories.

Side effects:
- Creates data/rag/series_1.db and data/rag/series_2.db (sqlite-vec stores)
- Loads bge-m3 into VRAM during indexing
- Does NOT touch the Obsidian vault (no vault_exporter.sync_series() call)
- Does NOT touch hime.db
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

# Hard-pin the env vars so the embeddings wrapper and path resolver find the
# local bge-m3 model and the target RAG directory.
os.environ["HIME_PROJECT_ROOT"] = "N:/Projekte/NiN/Hime"
os.environ["HIME_EMBEDDINGS_DIR"] = "N:/Projekte/NiN/Hime/modelle/embeddings"
os.environ["HIME_RAG_DIR"] = "N:/Projekte/NiN/Hime/data/rag"

# Ensure the backend package is importable
sys.path.insert(0, "N:/Projekte/NiN/Hime/app/backend")

from app.rag.chunker import ChunkPair  # noqa: E402
from app.rag.embeddings import embed_texts  # noqa: E402
from app.rag.store import SeriesStore  # noqa: E402


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
SOURCE_RE = re.compile(
    r"##\s*[^\n]*Source[^\n]*\n+>\s*(.+?)(?=\n\n|\n##|\Z)",
    re.DOTALL,
)
TRANSLATION_RE = re.compile(
    r"##\s*[^\n]*Translation[^\n]*\n+>\s*(.+?)(?=\n\n|\n##|\n---|\Z)",
    re.DOTALL,
)


def parse_chunk_file(path: Path) -> dict | None:
    """Parse a single Chunk_XXXX.md file into a dict suitable for ChunkPair."""
    text = path.read_text(encoding="utf-8")

    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        print(f"  [SKIP] {path.name}: no frontmatter")
        return None

    fm = fm_match.group(1)
    body = text[fm_match.end():]

    def _fm_int(key: str, default: int = 0) -> int:
        m = re.search(rf"^{key}:\s*(\d+)\s*$", fm, re.MULTILINE)
        return int(m.group(1)) if m else default

    book_id = _fm_int("book_id")
    chapter_id = _fm_int("chapter_id")
    paragraph_id = _fm_int("paragraph_id")
    chunk_index = _fm_int("chunk_index")

    src_match = SOURCE_RE.search(body)
    tgt_match = TRANSLATION_RE.search(body)
    if not src_match or not tgt_match:
        print(f"  [SKIP] {path.name}: missing source or translation section")
        return None

    source_text = src_match.group(1).strip()
    translated_text = tgt_match.group(1).strip()

    return {
        "book_id": book_id,
        "chapter_id": chapter_id,
        "paragraph_id": paragraph_id,
        "chunk_index": chunk_index,
        "source_text": source_text,
        "translated_text": translated_text,
    }


def reindex_series(series_id: int) -> dict:
    vault_dir = Path("N:/Projekte/NiN/Hime/obsidian-vault") / f"series_{series_id}"
    if not vault_dir.exists():
        return {"series_id": series_id, "error": f"vault dir missing: {vault_dir}"}

    md_files = sorted(vault_dir.glob("Chunk_*.md"))
    print(f"[series_{series_id}] found {len(md_files)} markdown chunks in {vault_dir}")

    # Parse all files
    parsed: list[dict] = []
    for md in md_files:
        d = parse_chunk_file(md)
        if d is not None:
            parsed.append(d)
    print(f"[series_{series_id}] parsed {len(parsed)} valid chunks")

    if not parsed:
        return {"series_id": series_id, "error": "no valid chunks", "chunks": 0}

    # Build ChunkPair objects (re-numbering chunk_index for determinism)
    chunks: list[ChunkPair] = []
    for new_idx, d in enumerate(parsed):
        chunks.append(ChunkPair(
            book_id=d["book_id"],
            chapter_id=d["chapter_id"],
            paragraph_id=d["paragraph_id"],
            source_text=d["source_text"],
            translated_text=d["translated_text"],
            chunk_index=new_idx,
        ))

    # Real bge-m3 inference — this loads the model into VRAM on first call
    t0 = time.time()
    texts_to_embed = [f"{c.source_text}\n{c.translated_text}" for c in chunks]
    print(f"[series_{series_id}] embedding {len(texts_to_embed)} chunks with bge-m3...")
    embeddings = embed_texts(texts_to_embed)
    t1 = time.time()
    print(f"[series_{series_id}] embedding took {t1 - t0:.2f}s "
          f"({len(embeddings)} vectors of dim {len(embeddings[0]) if embeddings else 0})")

    # Write into SeriesStore
    rag_dir = Path("N:/Projekte/NiN/Hime/data/rag")
    rag_dir.mkdir(parents=True, exist_ok=True)
    db_path = rag_dir / f"series_{series_id}.db"
    # Wipe any existing store to make the re-index deterministic
    if db_path.exists():
        db_path.unlink()

    store = SeriesStore(db_path)
    store.initialize()
    before = store.count()
    store.insert_chunks(chunks, embeddings)
    after = store.count()
    store.close()

    print(f"[series_{series_id}] store: {before} -> {after} rows (+{after - before})")
    return {
        "series_id": series_id,
        "chunks": after,
        "inserted": after - before,
        "embed_seconds": round(t1 - t0, 3),
        "db_path": str(db_path),
    }


def main() -> None:
    results = []
    for sid in (1, 2):
        print(f"\n=== Re-indexing series_{sid} ===")
        res = reindex_series(sid)
        results.append(res)
        print(f"[series_{sid}] result: {res}")

    print("\n=== SUMMARY ===")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
