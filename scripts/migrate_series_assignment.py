"""
SKELETT-MIGRATION: series_id assignment fuer Production Books.

NICHT AUSFUEHREN ohne manuelles Review des diagnose_series_assignment.py Outputs.
Nur nach expliziter Freigabe durch Luca ausfuehren.
VOR dem Live-Run: hime.db Backup anlegen.

Dry-run:   python scripts/migrate_series_assignment.py --dry-run
Live-run:  python scripts/migrate_series_assignment.py --live
           (fragt nochmal nach Bestaetigung)
"""
import argparse
import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# TODO: Luca fuellt diese Mapping-Tabelle nach Review des diagnose-Outputs aus.
# Format: book_id (int) -> series_name (str)
# Buecher ohne Eintrag bleiben unveraendert.
# ---------------------------------------------------------------------------
BOOK_TO_SERIES: dict[int, str] = {
    # Beispiele (PLATZHALTER -- echte Werte nach diagnose-Output eintragen):
    # 1: "Sakura Series",
    # 2: "Sakura Series",
    # 3: "Hana no Yume",
}


def run_migration(db_path: Path, dry_run: bool) -> None:
    mode = "DRYRUN" if dry_run else "LIVE"
    print(f"[migrate] Mode: {mode}")
    print(f"[migrate] DB: {db_path.resolve()}")

    if not BOOK_TO_SERIES:
        print()
        print("WARNING: BOOK_TO_SERIES mapping is empty -- nothing to migrate.")
        print("    Fill in the mapping based on diagnose_series_assignment.py output,")
        print("    then re-run.")
        return

    # Read-only for dry-run, read-write for live
    uri = f"file:{db_path}{'?mode=ro' if dry_run else ''}"
    conn = sqlite3.connect(uri, uri=True)

    try:
        for book_id, series_name in BOOK_TO_SERIES.items():
            row = conn.execute(
                "SELECT id FROM series WHERE name = ?", (series_name,)
            ).fetchone()

            if row:
                series_id = row[0]
            else:
                if dry_run:
                    print(f"  [DRYRUN] Would CREATE series: {series_name!r}")
                    series_id = -1
                else:
                    cur = conn.execute(
                        "INSERT INTO series (name) VALUES (?)", (series_name,)
                    )
                    series_id = cur.lastrowid
                    print(f"  [LIVE] Created series: {series_name!r} id={series_id}")

            book = conn.execute(
                "SELECT title FROM books WHERE id = ?", (book_id,)
            ).fetchone()
            title = book[0] if book else f"(unknown book {book_id})"

            if dry_run:
                print(
                    f"  [DRYRUN] Would SET books.series_id={series_id} "
                    f"WHERE id={book_id} ({title!r})"
                )
            else:
                conn.execute(
                    "UPDATE books SET series_id = ? WHERE id = ?", (series_id, book_id)
                )
                print(f"  [LIVE] Updated book {book_id} ({title!r}) -> series_id={series_id}")

        if not dry_run:
            conn.commit()
            print("[migrate] Committed.")

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(__file__).parent.parent / "hime.db",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.live:
        print("WARNING: LIVE MODE -- DB will be modified.")
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            import sys; sys.exit(0)

    run_migration(args.db_path, dry_run=args.dry_run)
