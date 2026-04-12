# scripts/shuukura_rag/phase_06_glossary.py
"""
Phase 6: Eigennamen aus den aligned Pairs extrahieren und ins Glossar eintragen.

Strategie:
  - fugashi POS-Tagging: 固有名詞 (Proper Noun) + 人名 (Person Name)
  - EN-Reading: häufigstes großgeschriebenes Wort in den EN-Pairs dieses JP-Namens
  - Confidence: High (>=10 Vorkommen, >=70% EN-Konsistenz),
                Medium (>=3 Vorkommen, >=50% EN-Konsistenz),
                Low (Rest)
  - High + Medium -> glossary_terms in Hime-DB
  - Low -> data/rag/staging/shuukura/glossary_low_confidence.json

Schreibt in: glossaries + glossary_terms Tabellen der Hime-DB.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Windows-Konsole: UTF-8 erzwingen
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import STAGING_DIR, halt, load_state, save_state, write_report


def load_all_aligned_pairs() -> list[dict]:
    """Lädt alle aligned Pairs aller Bände."""
    pairs = []
    for f in sorted(STAGING_DIR.glob("aligned_band_*.jsonl")):
        for line in f.read_text(encoding="utf-8").strip().splitlines():
            pairs.append(json.loads(line))
    return pairs


def extract_proper_nouns(jp_text: str, tagger) -> list[str]:
    """Extrahiert Eigennamen (固有名詞) mit fugashi."""
    names = []
    try:
        for word in tagger(jp_text):
            feature = word.feature
            feature_str = str(feature)
            if "固有名詞" in feature_str and ("人名" in feature_str or "一般" in feature_str):
                surf = word.surface
                if len(surf) >= 2:
                    names.append(surf)
    except Exception:
        pass
    return names


def extract_en_candidates(en_text: str) -> list[str]:
    """Extrahiert großgeschriebene Wörter aus EN-Text als Namenskandidaten."""
    words = re.findall(r"\b([A-Z][a-z]{2,})\b", en_text)
    return words


def build_glossary_candidates(pairs: list[dict]) -> dict[str, dict]:
    """
    Gibt {jp_name: {"en_counts": Counter, "occurrence_count": int}} zurück.
    """
    try:
        import fugashi
        tagger = fugashi.Tagger()
    except ImportError:
        halt(
            "fugashi nicht installiert.\n"
            "Fix: pip install fugashi unidic-lite"
        )

    name_data: dict[str, dict] = {}

    for pair in pairs:
        jp = pair.get("jp", "")
        en = pair.get("en", "")
        names = extract_proper_nouns(jp, tagger)
        en_candidates = extract_en_candidates(en)

        for name in names:
            if name not in name_data:
                name_data[name] = {"en_counts": Counter(), "occurrence_count": 0}
            name_data[name]["occurrence_count"] += 1
            for en_word in en_candidates:
                name_data[name]["en_counts"][en_word] += 1

    return name_data


def score_entry(jp: str, data: dict) -> tuple[str, str | None, float]:
    """Gibt (confidence, best_en, consistency_ratio) zurück."""
    count = data["occurrence_count"]
    if not data["en_counts"]:
        return "low", None, 0.0

    best_en, best_count = data["en_counts"].most_common(1)[0]
    total_en = sum(data["en_counts"].values())
    consistency = best_count / total_en if total_en > 0 else 0.0

    if count >= 10 and consistency >= 0.70:
        return "high", best_en, consistency
    if count >= 3 and consistency >= 0.50:
        return "medium", best_en, consistency
    return "low", best_en, consistency


def get_or_create_glossary(conn: sqlite3.Connection, series_id: int) -> int:
    """Gibt glossary_id zurück. Legt Glossar an falls nicht vorhanden."""
    row = conn.execute(
        "SELECT id FROM glossaries WHERE series_id = ? AND book_id IS NULL",
        (series_id,)
    ).fetchone()
    if row:
        return row["id"]
    conn.execute(
        "INSERT INTO glossaries (series_id, created_at, updated_at) VALUES (?, ?, ?)",
        (series_id, datetime.now(timezone.utc).isoformat(),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM glossaries WHERE series_id = ? AND book_id IS NULL",
        (series_id,)
    ).fetchone()["id"]


def check_glossary_tables(conn: sqlite3.Connection) -> bool:
    """Prüft ob glossaries und glossary_terms Tabellen existieren."""
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    return "glossaries" in tables and "glossary_terms" in tables


def main() -> None:
    print("\n=== Phase 6: Glossar-Extraktion ===\n")
    state = load_state()

    hime_db = state.get("hime_db")
    series_id = state.get("series_id")
    if not hime_db or not series_id:
        halt("hime_db/series_id fehlt — Phase 0 ausfuehren.")

    pairs = load_all_aligned_pairs()
    if not pairs:
        halt("Keine aligned Pairs gefunden — Phase 4 zuerst ausfuehren.")
    print(f"Lade {len(pairs)} aligned Pairs ...")

    print("Extrahiere Eigennamen (fugashi) ...")
    name_data = build_glossary_candidates(pairs)
    print(f"Rohe Eigennamen-Kandidaten: {len(name_data)}")

    # Confidence-Scoring
    high_medium: list[dict] = []
    low: list[dict] = []

    for jp, data in sorted(name_data.items(), key=lambda x: -x[1]["occurrence_count"]):
        confidence, best_en, ratio = score_entry(jp, data)
        entry = {
            "jp": jp,
            "en": best_en,
            "confidence": confidence,
            "occurrences": data["occurrence_count"],
            "consistency": round(ratio, 3),
        }
        if confidence in ("high", "medium"):
            high_medium.append(entry)
        else:
            low.append(entry)

    print(f"  High/Medium: {len(high_medium)}, Low: {len(low)}")

    # Glossar-Tabellen prüfen
    conn = sqlite3.connect(hime_db)
    conn.row_factory = sqlite3.Row

    if not check_glossary_tables(conn):
        print("  [WARNUNG] glossaries/glossary_terms Tabellen fehlen in DB — überspringe DB-Eintrag.")
        conn.close()
        glossary_id = None
        inserted = 0
    else:
        glossary_id = get_or_create_glossary(conn, series_id)
        inserted = 0

        for entry in high_medium:
            if not entry["en"]:
                continue
            existing = conn.execute(
                "SELECT id FROM glossary_terms WHERE glossary_id = ? AND source_term = ?",
                (glossary_id, entry["jp"])
            ).fetchone()
            if not existing:
                try:
                    conn.execute(
                        """
                        INSERT INTO glossary_terms
                            (glossary_id, source_term, target_term, category, notes, occurrences)
                        VALUES (?, ?, ?, 'character', ?, ?)
                        """,
                        (
                            glossary_id,
                            entry["jp"],
                            entry["en"],
                            f"Auto-extrahiert aus {entry['occurrences']} Vorkommen "
                            f"(confidence={entry['confidence']}, consistency={entry['consistency']})",
                            entry["occurrences"],
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  [WARN] INSERT fehlgeschlagen fuer {entry['jp']}: {e}")

        conn.commit()
        conn.close()
        print(f"  {inserted} neue Eintraege in glossary_terms")

    # Low-Confidence in Datei
    low_file = STAGING_DIR / "glossary_low_confidence.json"
    low_file.write_text(
        json.dumps(low, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Low-Confidence: {low_file}")

    save_state({
        "glossary_id": glossary_id,
        "glossary_inserted": inserted,
        "glossary_low_count": len(low),
    })

    # Report
    rows = "\n".join(
        f"| {e['jp']} | {e['en']} | {e['confidence']} | {e['occurrences']} | {e['consistency']:.0%} |"
        for e in high_medium[:30]
    )
    write_report("06_glossary.md", f"""# Phase 6: Glossar-Extraktion

## High + Medium Confidence ({len(high_medium)} Eintraege, Top 30)

| JP | EN | Confidence | Vorkommen | EN-Konsistenz |
|---|---|---|---|---|
{rows}

## Low Confidence ({len(low)} Eintraege)
Datei: `data/rag/staging/shuukura/glossary_low_confidence.json`
Manuelles Review durch Luca empfohlen.

## In DB eingetragen
glossary_id={glossary_id} -> {inserted} neue glossary_terms-Eintraege
""")
    print("\n[OK] Phase 6 abgeschlossen.")


if __name__ == "__main__":
    main()
