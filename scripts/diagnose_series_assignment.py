"""
Diagnose: series_id and is_reviewed status for all books in hime.db (Root).

READ-ONLY — never writes to the database.
Opens the DB with sqlite3 uri=True mode=ro.

Usage:
    python scripts/diagnose_series_assignment.py
    python scripts/diagnose_series_assignment.py --db-path /path/to/hime.db
"""
import argparse
import sqlite3
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles (Japanese titles)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def diagnose(db_path: Path) -> None:
    print(f"[diagnose] Reading from: {db_path.resolve()}")
    print(f"[diagnose] Mode: READ-ONLY (sqlite uri mode=ro)")
    print()

    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    try:
        # --- Book-level summary ---
        # paragraphs has no direct book_id; join via chapters
        books = conn.execute("""
            SELECT
                b.id,
                b.title,
                b.series_id,
                COUNT(p.id) AS paragraph_count,
                SUM(CASE WHEN p.is_reviewed = 1 THEN 1 ELSE 0 END) AS reviewed_count
            FROM books b
            LEFT JOIN chapters c ON c.book_id = b.id
            LEFT JOIN paragraphs p ON p.chapter_id = c.id
            GROUP BY b.id, b.title, b.series_id
            ORDER BY b.id
        """).fetchall()

        print(f"{'ID':>4}  {'Title':<50}  {'series_id':>10}  {'Paragraphs':>10}  {'Reviewed':>8}")
        print("-" * 92)
        for row in books:
            sid = str(row["series_id"]) if row["series_id"] is not None else "NULL"
            title = (row["title"] or "")[:50]
            print(
                f"{row['id']:>4}  {title:<50}  "
                f"{sid:>10}  {row['paragraph_count']:>10}  {row['reviewed_count']:>8}"
            )

        # --- Summary counts ---
        total = len(books)
        null_series = sum(1 for r in books if r["series_id"] is None)
        no_reviewed = sum(1 for r in books if r["reviewed_count"] == 0)

        print()
        print(f"Total books:                      {total}")
        print(f"Books with series_id=NULL:        {null_series}")
        print(f"Books with 0 reviewed paragraphs: {no_reviewed}")

        if null_series == total:
            print()
            print("WARNING: ALL books have series_id=NULL — RAG indexing is blocked.")
            print("    Fix: assign series_id via migrate_series_assignment.py")
            print("         (requires manual review + explicit approval from Luca)")

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnose series_id and is_reviewed status")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(__file__).parent.parent / "hime.db",
        help="Path to hime.db (default: project root hime.db)",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    diagnose(args.db_path)
