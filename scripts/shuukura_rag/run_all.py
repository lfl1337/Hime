#!/usr/bin/env python
# scripts/shuukura_rag/run_all.py
"""
Master-Runner: führt alle Shuukura-RAG-Phasen 0-7 sequenziell aus.

Verwendung:
    python scripts/shuukura_rag/run_all.py [--from-phase N] [--to-phase M]

Optionen:
    --from-phase N   Start ab Phase N (Standard: 0)
    --to-phase M     Stopp nach Phase M (Standard: 7)

Beispiele:
    python scripts/shuukura_rag/run_all.py              # alle Phasen
    python scripts/shuukura_rag/run_all.py --from-phase 5   # ab Phase 5
    python scripts/shuukura_rag/run_all.py --from-phase 1 --to-phase 3
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts" / "shuukura_rag"
PYTHON = sys.executable

PHASES = [
    (0, "phase_00_inspect.py",  "Setup & Inspektion"),
    (1, "phase_01_extract.py",  "JP-EPUBs entpacken"),
    (2, "phase_02_parse.py",    "EPUB-Parsing"),
    (3, "phase_03_match.py",    "Band-Matching"),
    (4, "phase_04_align.py",    "Sentence-Alignment (lang)"),
    (5, "phase_05_import.py",   "DB-Import + RAG-Indexierung"),
    (6, "phase_06_glossary.py", "Glossar-Extraktion"),
    (7, "phase_07_report.py",   "Final Report"),
]


def run_phase(nr: int, script: str, desc: str) -> bool:
    """Führt eine Phase aus. Gibt True bei Erfolg zurück."""
    print(f"\n{'='*60}")
    print(f"Phase {nr}: {desc}")
    print(f"{'='*60}")
    start = time.time()
    result = subprocess.run(
        [PYTHON, "-X", "utf8", "-W", "ignore", str(SCRIPTS_DIR / script)],
        cwd=str(ROOT),
    )
    elapsed = time.time() - start
    if result.returncode == 0:
        print(f"\n[OK] Phase {nr} abgeschlossen ({elapsed:.0f}s)")
        return True
    else:
        print(f"\n[FEHLER] Phase {nr} fehlgeschlagen (returncode={result.returncode})")
        return False


def main() -> None:
    args = sys.argv[1:]
    from_phase = 0
    to_phase = 7

    i = 0
    while i < len(args):
        if args[i] == "--from-phase" and i + 1 < len(args):
            from_phase = int(args[i + 1])
            i += 2
        elif args[i] == "--to-phase" and i + 1 < len(args):
            to_phase = int(args[i + 1])
            i += 2
        else:
            i += 1

    print(f"\nShuukura RAG Pipeline — Phasen {from_phase} bis {to_phase}")
    print(f"Python: {PYTHON}\n")

    total_start = time.time()
    for nr, script, desc in PHASES:
        if nr < from_phase or nr > to_phase:
            continue
        ok = run_phase(nr, script, desc)
        if not ok:
            print(f"\nPipeline gestoppt bei Phase {nr}.")
            sys.exit(1)

    total = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"Pipeline komplett! Gesamtzeit: {total/60:.1f} Minuten")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
