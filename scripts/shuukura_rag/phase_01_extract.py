# scripts/shuukura_rag/phase_01_extract.py
"""
Phase 1: JP-EPUBs aus dem RAR-Archiv entpacken.

Ergebnis: data/raw_imports/shuukura/jp_extracted/*.epub (8 Bände)
EN-EPUBs sind bereits fertig in data/epubs/Shuukura/ — kein Entpacken nötig.

Erzeugt: reports/.../01_extraction.md
State: jp_epub_dir, en_epub_dir, jp_epubs (Liste), en_epubs (Liste)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Windows-Konsole: UTF-8 erzwingen (JP-Dateinamen)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import EN_EPUB_DIR, RAW_JP_DIR, ROOT, halt, load_state, save_state, write_report

# 7-Zip als rarfile-Backend konfigurieren (kein WinRAR/unrar nötig)
_7ZIP = Path("C:/Program Files/7-Zip/7z.exe")


def extract_rar(rar_path: Path, dst: Path) -> None:
    """Entpackt ein einzelnes RAR-Archiv nach dst (via 7-Zip)."""
    if not _7ZIP.exists():
        halt("7-Zip nicht gefunden: C:/Program Files/7-Zip/7z.exe")
    result = subprocess.run(
        [str(_7ZIP), "x", str(rar_path), f"-o{dst}", "-y"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        halt(f"7-Zip Extraktion fehlgeschlagen fuer {rar_path.name}:\n{result.stderr}")


def extract_jp_rar() -> Path:
    """
    Entpackt das aeussere RAR-Archiv und alle darin enthaltenen inneren RAR-Archive.
    Manche Pakete sind verschachtelt: outer.rar -> inner01-07.rar + inner08.rar -> *.epub
    """
    rar_files = sorted(RAW_JP_DIR.glob("*.rar"))
    if not rar_files:
        halt(f"Kein .rar-Archiv in {RAW_JP_DIR} gefunden.")

    rar_path = rar_files[0]
    dst = RAW_JP_DIR / "jp_extracted"
    dst.mkdir(parents=True, exist_ok=True)

    print(f"Entpacke (Level 1): {rar_path.name}")
    extract_rar(rar_path, dst)

    # Prüfen ob innere RARs extrahiert wurden — rekursiv entpacken
    inner_rars = sorted(dst.rglob("*.rar"))
    if inner_rars:
        print(f"  -> {len(inner_rars)} innere RAR(s) gefunden, entpacke...")
        for inner in inner_rars:
            print(f"     Entpacke (Level 2): {inner.name}")
            extract_rar(inner, dst)

    epubs = sorted(dst.rglob("*.epub"))
    print(f"  -> {len(epubs)} EPUB(s) extrahiert")
    for e in epubs:
        print(f"    {e.name}  ({e.stat().st_size // 1024} KB)")

    return dst


def main() -> None:
    print("\n=== Phase 1: Entpacken ===\n")
    state = load_state()

    # JP entpacken
    jp_extract_dir = extract_jp_rar()
    jp_epubs = sorted(jp_extract_dir.rglob("*.epub"))

    # EN ist bereits fertig
    en_epubs = sorted(EN_EPUB_DIR.glob("*.epub"))
    print(f"\nEN-EPUBs in {EN_EPUB_DIR}: {len(en_epubs)} Datei(en)")
    for e in en_epubs:
        print(f"  {e.name}  ({e.stat().st_size // 1024} KB)")

    if len(jp_epubs) != 8:
        print(f"\n[WARNUNG] Erwartung: 8 JP-EPUBs, gefunden: {len(jp_epubs)}. Weiter mit vorhandenem.")

    save_state({
        "jp_epub_dir": str(jp_extract_dir),
        "en_epub_dir": str(EN_EPUB_DIR),
        "jp_epubs": [str(e) for e in jp_epubs],
        "en_epubs": [str(e) for e in en_epubs],
    })

    # Originale nicht anfassen — nur prüfen
    rar_files = sorted(RAW_JP_DIR.glob("*.rar"))
    for r in rar_files:
        assert r.exists(), f"Original-RAR verschwunden: {r}"

    # .gitignore prüfen / ergänzen
    gitignore = ROOT / ".gitignore"
    ignore_patterns = [
        "data/raw_imports/shuukura/jp_extracted/",
        "data/rag/staging/",
    ]
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        to_add = [p for p in ignore_patterns if p not in existing]
        if to_add:
            with gitignore.open("a", encoding="utf-8") as f:
                f.write("\n# Shuukura RAG pipeline (auto-added)\n")
                for p in to_add:
                    f.write(p + "\n")
            print(f"\n.gitignore ergänzt: {to_add}")

    # Report
    jp_lines = "\n".join(
        f"| {e.name} | {e.stat().st_size // 1024} KB |" for e in jp_epubs
    )
    en_lines = "\n".join(
        f"| {e.name} | {e.stat().st_size // 1024} KB |" for e in en_epubs
    )
    write_report("01_extraction.md", f"""# Phase 1: Entpacken

## JP-EPUBs (aus RAR)
| Datei | Groesse |
|---|---|
{jp_lines}

**Total: {len(jp_epubs)} Baende**

## EN-EPUBs (bereits entpackt)
| Datei | Groesse |
|---|---|
{en_lines}

**Total: {len(en_epubs)} Baende**

## Originale
- RAR-Archiv: vorhanden, unveraendert OK
""")
    print("\n[OK] Phase 1 abgeschlossen.")


if __name__ == "__main__":
    main()
