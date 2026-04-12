# scripts/shuukura_rag/phase_07_report.py
"""Phase 7: Finaler Abschluss-Report."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Windows-Konsole: UTF-8 erzwingen
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import ROOT, load_state, write_report


def main() -> None:
    print("\n=== Phase 7: Final Report ===\n")
    state = load_state()

    timestamp = state.get("timestamp", "?")
    series_id = state.get("series_id", "?")
    import_stats = state.get("import_stats", [])
    total_rag = state.get("total_rag_chunks", "?")
    glossary_inserted = state.get("glossary_inserted", "?")
    glossary_low = state.get("glossary_low_count", "?")
    hime_db = state.get("hime_db", "?")
    rag_backup = state.get("rag_backup", "keines")
    alignment_stats = state.get("alignment_stats", [])

    bilingual = [s for s in import_stats if not s.get("mono")]
    mono = [s for s in import_stats if s.get("mono")]
    total_para = sum(s["paragraphs"] for s in import_stats)
    total_aligned = sum(s.get("pairs", 0) for s in alignment_stats)

    # git log
    git_log = subprocess.run(
        ["git", "log", "--oneline", "-10"],
        capture_output=True, text=True, cwd=str(ROOT)
    ).stdout.strip()

    import_rows = "\n".join(
        f"| {s['band']:02d} | {s.get('book_id','?')} | {s['paragraphs']} "
        f"| {'—' if s.get('mono') else 'ja'} |"
        for s in import_stats
    )

    align_rows = "\n".join(
        f"| {s['band']:02d} | {s.get('pairs', '?')} | {s.get('confidence','?')} |"
        for s in alignment_stats
    )

    content = f"""# Shuukura RAG Indexing — Final Report
**Datum:** {timestamp}
**Branch:** main

---

## TL;DR

- {len(bilingual)} bilinguale JP+EN-Baende importiert und indexiert
- {len(mono)} monolingualer JP-Band importiert (nicht indexiert, kein EN-Pendant)
- {total_rag} RAG-Chunks in `series_{series_id}.db`
- {total_para} Paragraphen total in Hime-DB
- {total_aligned} aligned Sentence-Pairs (bertalign)
- series_id={series_id} fuer alle Shuukura-Baende
- {glossary_inserted} Glossar-Eintraege (High/Medium) automatisch extrahiert
- {glossary_low} Low-Confidence-Eintraege -> manuelles Review noetig

---

## Alignment-Stats (Phase 4)

| Band | Pairs | Confidence |
|---|---|---|
{align_rows}

---

## Import-Stats (Phase 5)

| Band | Book-ID | Paragraphen | RAG-indexiert |
|---|---|---|---|
{import_rows}

---

## Geaenderte Dateien & DB

- **Hime-DB** (`{hime_db}`):
  +{len(import_stats)} Books, +{total_para} Paragraphs, +{glossary_inserted} GlossaryTerms
- **RAG-DB** (`data/rag/series_{series_id}.db`): {total_rag} Chunks
- **Filesystem**:
  - `data/raw_imports/shuukura/jp_extracted/` — extrahierte JP-EPUBs
  - `data/rag/staging/shuukura/` — Zwischenergebnisse (in .gitignore)
  - `reports/shuukura_rag_{timestamp}/` — Reports aller Phasen
  - `data/rag/staging/shuukura/glossary_low_confidence.json` — manuelles Review
- **RAG-Backup:** {rag_backup}

---

## Offene Punkte

1. **Manuelles Glossar-Review:**
   `data/rag/staging/shuukura/glossary_low_confidence.json` ({glossary_low} Eintraege)
2. **WN<->LN Alignment Baende 1+2:** Qualitaet pruefen, ggf. manuell korrigieren.
3. **RAG-Rauch-Test:** Hime starten, Shuukura-Kapitel uebersetzen, pruefen ob RAG-Kontext erscheint.

---

## Letzte Commits

```
{git_log}
```
"""
    write_report("07_final_report.md", content)
    print(f"[report] {state.get('report_dir')}/07_final_report.md")
    print("\n[OK] Phase 7 abgeschlossen — Pipeline komplett.")


if __name__ == "__main__":
    main()
