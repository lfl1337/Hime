# scripts/shuukura_rag/phase_03_match.py
"""
Phase 3: JP-Bände mit EN-Bänden matchen.

Matching-Strategie:
  1. Primär: Bandnummer aus Dateiname (extract_band_number aus Phase 2)
  2. EN Vol 1/2 sind WN-Versionen — Matching zu JP Vol 1/2 mit Confidence 'medium'
  3. JP Band 8 hat kein EN-Pendant -> monolingual

HALT: Falls <7 Paare gefunden werden oder ein Paar Confidence 'low' hat.

Erzeugt: reports/.../03_band_matching.md
State:   matched_pairs, mono_jp_band
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows-Konsole: UTF-8 erzwingen
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import STAGING_DIR, halt, load_state, save_state, write_report


# WN-Bände werden schlechter aligniert als LN<->LN
WN_BAND_NUMBERS = {1, 2}


def load_parsed_bands(lang: str) -> dict[int, dict]:
    """Lädt alle geparsten Bände einer Sprache. Key = Bandnummer."""
    bands: dict[int, dict] = {}
    for f in sorted(STAGING_DIR.glob(f"shuukura_{lang}_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        nr = data["band"]
        data["_path"] = str(f)
        bands[nr] = data
    return bands


def match_bands(
    jp_bands: dict[int, dict],
    en_bands: dict[int, dict],
) -> tuple[list[dict], list[dict]]:
    """
    Gibt (matched_pairs, mono_jp_bands) zurück.

    matched_pairs = [
      {"jp_band": 1, "en_band": 1, "jp_file": "...", "en_file": "...",
       "confidence": "medium", "note": "WN<->LN mismatch"},
      ...
    ]
    """
    pairs: list[dict] = []
    unmatched_jp: list[dict] = []

    for jp_nr, jp_data in sorted(jp_bands.items()):
        if jp_nr in en_bands:
            en_data = en_bands[jp_nr]
            # WN-Bände (1+2): medium confidence
            if jp_nr in WN_BAND_NUMBERS:
                confidence = "medium"
                note = "EN ist WN-Version, JP ist LN — Alignment qualitativ schlechter"
            else:
                confidence = "high"
                note = "LN<->LN direktes Number-Matching"

            pairs.append({
                "jp_band": jp_nr,
                "en_band": jp_nr,
                "jp_file": jp_data["_path"],
                "en_file": en_data["_path"],
                "confidence": confidence,
                "note": note,
            })
        else:
            unmatched_jp.append({
                "jp_band": jp_nr,
                "jp_file": jp_data["_path"],
            })

    return pairs, unmatched_jp


def main() -> None:
    print("\n=== Phase 3: Band-Matching ===\n")

    jp_bands = load_parsed_bands("jp")
    en_bands = load_parsed_bands("en")

    print(f"JP-Baende: {sorted(jp_bands.keys())}")
    print(f"EN-Baende: {sorted(en_bands.keys())}")

    pairs, mono_jp = match_bands(jp_bands, en_bands)

    print(f"\nMatched: {len(pairs)} Paare")
    for p in pairs:
        print(f"  JP {p['jp_band']:02d} <-> EN {p['en_band']:02d}  [{p['confidence']}]  {p['note']}")

    print(f"\nMonolingual JP (kein EN-Pendant): {[m['jp_band'] for m in mono_jp]}")

    # HALT-Bedingungen
    low_pairs = [p for p in pairs if p["confidence"] == "low"]
    if low_pairs:
        halt(
            f"{len(low_pairs)} Paar(e) mit Confidence 'low' — manuelles Review nötig:\n"
            + "\n".join(f"  JP {p['jp_band']} <-> EN {p['en_band']}" for p in low_pairs)
        )

    if len(pairs) < 7:
        halt(
            f"Nur {len(pairs)} Paare gefunden, erwartet 7. "
            "Dateinamen-Parsing prüfen und ggf. manuell korrigieren."
        )

    save_state({
        "matched_pairs": pairs,
        "mono_jp_bands": mono_jp,
    })

    # Report
    rows = "\n".join(
        f"| {p['jp_band']:02d} | `{Path(p['jp_file']).name[:50]}` "
        f"| {p['en_band']:02d} | `{Path(p['en_file']).name[:50]}` "
        f"| {p['confidence']} | {p['note']} |"
        for p in pairs
    )
    mono_rows = "\n".join(
        f"| {m['jp_band']:02d} | `{Path(m['jp_file']).name[:50]}` | — | — | mono only | |"
        for m in mono_jp
    )

    write_report("03_band_matching.md", f"""# Phase 3: Band-Matching

| JP Band | JP File | EN Band | EN File | Confidence | Note |
|---|---|---|---|---|---|
{rows}
{mono_rows}

**Bilinguale Paare: {len(pairs)}**
**Monolinguale JP-Baende: {len(mono_jp)}**

## Hinweis WN vs LN
EN Baende 1 und 2 sind Web-Novel-Versionen. Das Alignment JP LN <-> EN WN
ist qualitativ schlechter als LN<->LN. Die resultierenden Chunks sind
verwendbar aber weniger praezise. Manuelles Nachkorrigieren fuer kritische
Szenen empfohlen.
""")
    print("\n[OK] Phase 3 abgeschlossen.")


if __name__ == "__main__":
    main()
