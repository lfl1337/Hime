# scripts/shuukura_rag/phase_00_inspect.py
"""
Phase 0: Verzeichnis-Inspektion, Tool-Check, DB-Status, RAG-Backup.

Erzeugt:
  - data/rag/staging/shuukura/state.json  (report_dir, hime_db, series_id)
  - reports/shuukura_rag_YYYYMMDD_HHMM/00_inspection.md
  - data/rag/.backup_YYYYMMDD_HHMM/ (falls RAG-DB nicht leer)

HALT-Bedingungen:
  - rarfile NICHT installierbar und kein unrar im PATH
  - LaBSE-Download nötig für bertalign, aber noch nicht bestätigt
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from common import (EN_EPUB_DIR, RAW_JP_DIR, ROOT, STAGING_DIR,
                    halt, save_state, write_report)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")
REPORT_DIR = ROOT / "reports" / f"shuukura_rag_{TIMESTAMP}"


def inspect_source_files() -> tuple[list[Path], list[Path]]:
    """Listet RAR-Archive (JP) und EPUBs (EN) auf."""
    jp_files = sorted(RAW_JP_DIR.glob("*")) if RAW_JP_DIR.exists() else []
    en_files = sorted(EN_EPUB_DIR.glob("*.epub")) if EN_EPUB_DIR.exists() else []
    return jp_files, en_files


def check_tools() -> dict[str, bool]:
    """Prüft Verfügbarkeit aller benötigten Pakete."""
    results = {}

    # rarfile
    try:
        import rarfile  # noqa: F401
        results["rarfile"] = True
    except ImportError:
        results["rarfile"] = False

    # unrar binary (Fallback)
    results["unrar_binary"] = shutil.which("unrar") is not None

    # ebooklib
    try:
        import ebooklib  # noqa: F401
        results["ebooklib"] = True
    except ImportError:
        results["ebooklib"] = False

    # beautifulsoup4
    try:
        import bs4  # noqa: F401
        results["beautifulsoup4"] = True
    except ImportError:
        results["beautifulsoup4"] = False

    # fugashi (JP tokenizer)
    try:
        import fugashi  # noqa: F401
        results["fugashi"] = True
    except ImportError:
        results["fugashi"] = False

    # bertalign
    try:
        import bertalign  # noqa: F401
        results["bertalign"] = True
    except ImportError:
        results["bertalign"] = False

    # sentence_transformers (für BGE-M3 / LaBSE)
    try:
        import sentence_transformers  # noqa: F401
        results["sentence_transformers"] = True
    except ImportError:
        results["sentence_transformers"] = False

    return results


def find_hime_db() -> Path:
    """
    Pinnt die Produktions-hime.db.
    Regel: Nimm die DB mit den meisten Books.
    Falls beide leer sind: Root-DB bevorzugen.
    """
    candidates = [
        ROOT / "hime.db",
        ROOT / "app" / "backend" / "hime.db",
    ]
    best: Path | None = None
    best_count = -1
    for c in candidates:
        if not c.exists():
            continue
        try:
            conn = sqlite3.connect(str(c))
            row = conn.execute("SELECT COUNT(*) FROM books").fetchone()
            conn.close()
            count = row[0] if row else 0
        except Exception:
            count = 0
        print(f"  {c}  ->  {count} books")
        if count > best_count:
            best_count = count
            best = c
    if best is None:
        # Fallback: Root-DB anlegen (existiert noch nicht)
        best = ROOT / "hime.db"
    return best


def query_shuukura_series(db_path: Path) -> tuple[int | None, int, list[dict]]:
    """
    Sucht nach vorhandener Shuukura-Series in der Hime-DB.
    Gibt (series_id_existing, series_id_to_use, books_list) zurück.
    series_id_existing = None  →  Zustand A: Series existiert noch nicht.
    """
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT DISTINCT series_id, series_title FROM books "
        "WHERE series_title LIKE '%Shuukura%' OR series_title LIKE '%週に%' "
        "   OR series_title LIKE '%Classmate%'"
    ).fetchall()
    books = conn.execute(
        "SELECT id, title, series_id FROM books "
        "WHERE series_title LIKE '%Shuukura%' OR series_title LIKE '%週に%' "
        "   OR series_title LIKE '%Classmate%'"
    ).fetchall()
    conn.close()

    series_id_existing = rows[0][0] if rows else None

    # Nächste freie series_id bestimmen (falls neue angelegt werden muss)
    if series_id_existing is None:
        conn2 = sqlite3.connect(str(db_path))
        max_row = conn2.execute("SELECT MAX(series_id) FROM books").fetchone()
        conn2.close()
        max_id = max_row[0] if max_row and max_row[0] else 0
        series_id_new = max_id + 1
    else:
        series_id_new = series_id_existing

    book_list = [{"id": r[0], "title": r[1], "series_id": r[2]} for r in books]
    return (series_id_existing, series_id_new, book_list)


def backup_rag() -> str | None:
    """Backup von data/rag/ falls nicht leer."""
    rag_dir = ROOT / "data" / "rag"
    if not rag_dir.exists():
        return None
    # Nur .db-Dateien sichern (keine Verzeichnisse wie staging/)
    existing = [f for f in rag_dir.iterdir() if f.is_file() and f.suffix == ".db"]
    if not existing:
        return None
    backup_dir = rag_dir / f".backup_{TIMESTAMP}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for f in existing:
        shutil.copy2(f, backup_dir / f.name)
    return str(backup_dir)


def main() -> None:
    print(f"\n=== Phase 0: Inspektion ({TIMESTAMP}) ===\n")

    # Report-Ordner anlegen
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Report-Ordner: {REPORT_DIR}")

    # State initialisieren
    save_state({"report_dir": str(REPORT_DIR), "timestamp": TIMESTAMP})

    # 1) Quelldateien
    print("\n--- Quelldateien ---")
    jp_files, en_files = inspect_source_files()
    print(f"JP (raw_imports): {len(jp_files)} Datei(en)")
    for f in jp_files:
        print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")
    print(f"EN (epubs/Shuukura): {len(en_files)} EPUB(s)")
    for f in en_files:
        print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")

    # 2) Tools
    print("\n--- Tool-Verfügbarkeit ---")
    tools = check_tools()
    for name, ok in tools.items():
        status = "OK" if ok else "FEHLT"
        print(f"  [{status}] {name}")

    # HALT-Bedingungen prüfen
    if not tools["rarfile"] and not tools["unrar_binary"]:
        halt(
            "Weder 'rarfile' noch 'unrar' verfügbar.\n"
            "Fix: cd app/backend && uv pip install rarfile"
        )
    if not tools["ebooklib"] or not tools["beautifulsoup4"]:
        halt(
            "ebooklib oder beautifulsoup4 fehlt.\n"
            "Fix: cd app/backend && uv pip install ebooklib beautifulsoup4"
        )
    if not tools["bertalign"]:
        print(
            "\n[WARNUNG] bertalign nicht installiert.\n"
            "   bertalign braucht intern LaBSE (~2 GB HF-Download).\n"
            "   Fix: cd app/backend && uv pip install bertalign\n"
            "   Pipeline läuft bis Phase 3, dann HALT vor Phase 4."
        )
        save_state({"bertalign_available": False})
    else:
        save_state({"bertalign_available": True})

    if not tools["fugashi"]:
        print(
            "\n[WARNUNG] fugashi nicht installiert (wird für Glossar-Extraktion in Phase 6 gebraucht).\n"
            "   Fix: cd app/backend && uv pip install fugashi unidic-lite"
        )

    # 3) Hime-DB
    print("\n--- Hime-DB ---")
    hime_db = find_hime_db()
    print(f"Produktions-DB: {hime_db}")
    series_id_existing, series_id_to_use, existing_books = query_shuukura_series(hime_db)
    if series_id_existing is not None:
        print(f"  Zustand C/B: Series existiert mit series_id={series_id_existing}")
        print(f"  Vorhandene Bücher: {len(existing_books)}")
        for b in existing_books:
            print(f"    id={b['id']}  {b['title']}")
    else:
        print(f"  Zustand A: Keine Shuukura-Series -> neue series_id={series_id_to_use}")

    save_state({
        "hime_db": str(hime_db),
        "series_id": series_id_to_use,
        "series_id_existed": series_id_existing is not None,
        "existing_shuukura_books": existing_books,
    })

    # 4) RAG-Backup
    print("\n--- RAG-Backup ---")
    backup_path = backup_rag()
    if backup_path:
        print(f"  Backup erstellt: {backup_path}")
        save_state({"rag_backup": backup_path})
    else:
        print("  data/rag/ ist leer — kein Backup nötig.")
        save_state({"rag_backup": None})

    # Report schreiben
    report = f"""# Phase 0: Inspektion
Datum: {TIMESTAMP}

## Quelldateien

### JP (raw_imports/shuukura/)
{chr(10).join(f'- `{f.name}` — {f.stat().st_size // 1024} KB' for f in jp_files) or '*(keine)*'}

### EN (epubs/Shuukura/)
{chr(10).join(f'- `{f.name}` — {f.stat().st_size // 1024} KB' for f in en_files) or '*(keine)*'}

## Tool-Status
{chr(10).join(f'- {"OK" if ok else "FEHLT"} `{name}`' for name, ok in tools.items())}

## Hime-DB
- Pfad: `{hime_db}`
- Series-Status: {'Existiert (series_id=' + str(series_id_existing) + ')' if series_id_existing else 'Neu anlegen (series_id=' + str(series_id_to_use) + ')'}
- Vorhandene Shuukura-Bücher: {len(existing_books)}

## RAG-Backup
{('`' + str(backup_path) + '`') if backup_path else 'Nicht nötig (RAG war leer)'}

## State-Datei
`{ROOT / "data" / "rag" / "staging" / "shuukura" / "state.json"}`
"""
    write_report("00_inspection.md", report)
    print("\n[OK] Phase 0 abgeschlossen.")


if __name__ == "__main__":
    main()
