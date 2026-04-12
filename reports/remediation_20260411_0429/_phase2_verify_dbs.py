"""Verify series_1.db and series_2.db (Phase 2 Task 2.7 Step 6)."""
import sqlite3
import pathlib

for sid in (1, 2):
    path = pathlib.Path(f"N:/Projekte/NiN/Hime/data/rag/series_{sid}.db")
    if not path.exists():
        print(f"series_{sid}.db: MISSING")
        continue
    size = path.stat().st_size
    print(f"series_{sid}.db: exists, {size / 1024:.1f} KB")
    conn = sqlite3.connect(str(path))
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"  tables: {[t[0] for t in tables]}")
        for (t,) in tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t}: {n} rows")
            except Exception as e:
                print(f"  {t}: ERROR - {e}")
    finally:
        conn.close()
