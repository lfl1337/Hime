"""
Direct sqlite-vec smoke test for re-indexed series DBs.

Bypasses the backend router because app/backend/app/rag/store.py uses the
stale `LIMIT ?` syntax while sqlite-vec 0.1.9 requires `AND k = ?` on knn
queries. That's a pre-existing bug unrelated to Phase 2 — documented in the
report. This script performs the same logical smoke test using a real bge-m3
embedding of a JP query string and the correct sqlite-vec syntax.
"""
from __future__ import annotations

import json
import os
import sys
import sqlite3
from pathlib import Path

# Match the reindex script's env setup so embed_texts uses the local model
os.environ["HIME_PROJECT_ROOT"] = "N:/Projekte/NiN/Hime"
os.environ["HIME_EMBEDDINGS_DIR"] = "N:/Projekte/NiN/Hime/modelle/embeddings"
os.environ["HIME_RAG_DIR"] = "N:/Projekte/NiN/Hime/data/rag"

sys.path.insert(0, "N:/Projekte/NiN/Hime/app/backend")

import sqlite_vec  # noqa: E402
from app.rag.embeddings import embed_texts  # noqa: E402


QUERIES = {
    1: "\u5c11\u5973",  # 少女 ("girl")
    2: "\u5263",         # 剣 ("sword") — sample query for series 2
}

OUT_PATH = Path("N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/_phase2_rag_query_results.json")


def query_series(series_id: int, q_text: str, top_k: int = 3) -> dict:
    db_path = Path(f"N:/Projekte/NiN/Hime/data/rag/series_{series_id}.db")
    if not db_path.exists():
        return {"series_id": series_id, "error": "db not found"}

    # Encode the query with bge-m3
    q_vec = embed_texts([q_text])[0]

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    try:
        rows = conn.execute(
            """
            SELECT c.book_id, c.chapter_id, c.paragraph_id,
                   c.source_text, c.translated_text, v.distance
            FROM chunk_vectors v
            JOIN chunks c ON c.id = v.chunk_id
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (json.dumps(q_vec), top_k),
        ).fetchall()
    finally:
        conn.close()

    results = []
    for r in rows:
        results.append({
            "book_id": r[0],
            "chapter_id": r[1],
            "paragraph_id": r[2],
            "source_text": r[3],
            "translated_text": r[4],
            "distance": float(r[5]),
        })
    return {"series_id": series_id, "query": q_text, "top_k": top_k, "results": results}


def main() -> None:
    all_out = []
    for sid, qt in QUERIES.items():
        res = query_series(sid, qt, top_k=3)
        print(f"[series_{sid}] query={qt!r} got {len(res.get('results', []))} results")
        if "error" in res:
            print(f"  ERROR: {res['error']}")
        else:
            for i, r in enumerate(res["results"]):
                print(f"  [{i}] dist={r['distance']:.4f} pid={r['paragraph_id']} "
                      f"src_len={len(r['source_text'])} tgt_len={len(r['translated_text'])}")
        all_out.append(res)

    OUT_PATH.write_text(json.dumps(all_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFull results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
