# scripts/shuukura_rag/phase_04_align.py
"""
Phase 4: Sentence-Alignment aller 7 JP<->EN Band-Paare mit bertalign.

Output: data/rag/staging/shuukura/aligned_band_01.jsonl .. aligned_band_07.jsonl

Format pro Zeile:
{"jp": "...", "en": "...", "chapter_idx": 0, "para_idx": 0, "band": 1,
 "confidence": "high"}

Laufzeit: ~1-3 Stunden (CPU). Kein HALT ausser bertalign nicht verfügbar.
Idempotent: bereits alignierte Bände werden übersprungen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows-Konsole: UTF-8 erzwingen
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import STAGING_DIR, halt, load_state, save_state, write_report


def collect_sentences(band_data: dict) -> list[tuple[int, int, str]]:
    """
    Gibt eine flache Liste von (chapter_idx, para_idx, sentence) zurück.
    Alle Sätze aus allen Kapiteln, in Reihenfolge.
    """
    result = []
    for ch_idx, ch in enumerate(band_data["chapters"]):
        for pa_idx, para in enumerate(ch["paragraphs"]):
            for sent in para["sentences"]:
                result.append((ch_idx, pa_idx, sent))
    return result


def extract_pairs_from_result(aligner_result, jp_sents, en_sents) -> list[dict]:
    """
    Extrahiert (jp_text, en_text) Paare aus dem bertalign-Ergebnis.

    bertalign gibt result als Liste von (src_indices, tgt_indices) zurück:
      result = [([0], [0]), ([1, 2], [1]), ...]
    """
    pairs = []
    for src_idxs, tgt_idxs in aligner_result:
        jp_text = " ".join(jp_sents[int(i)][2] for i in src_idxs if int(i) < len(jp_sents))
        en_text = " ".join(en_sents[int(i)][2] for i in tgt_idxs if int(i) < len(en_sents))
        if jp_text.strip() and en_text.strip():
            ch_idx = jp_sents[int(src_idxs[0])][0] if src_idxs else 0
            pa_idx = jp_sents[int(src_idxs[0])][1] if src_idxs else 0
            pairs.append({
                "jp": jp_text,
                "en": en_text,
                "chapter_idx": ch_idx,
                "para_idx": pa_idx,
            })
    return pairs


def align_band_pair(pair: dict) -> list[dict]:
    """Aligniert ein einzelnes JP<->EN Band-Paar."""
    from bertalign import Bertalign

    jp_data = json.loads(Path(pair["jp_file"]).read_text(encoding="utf-8"))
    en_data = json.loads(Path(pair["en_file"]).read_text(encoding="utf-8"))
    band_nr = pair["jp_band"]

    jp_sents = collect_sentences(jp_data)
    en_sents = collect_sentences(en_data)

    jp_text = "\n".join(s[2] for s in jp_sents)
    en_text = "\n".join(s[2] for s in en_sents)

    print(f"  Band {band_nr:02d}: {len(jp_sents)} JP-Saetze, {len(en_sents)} EN-Saetze", flush=True)

    # is_split=True: wir haben bereits segmentierte Sätze, bypass sentence splitter
    aligner = Bertalign(jp_text, en_text, is_split=True)
    aligner.align_sents()

    aligned_pairs = extract_pairs_from_result(aligner.result, jp_sents, en_sents)
    print(f"    -> {len(aligned_pairs)} aligned Pairs", flush=True)

    # Mit Metadaten anreichern
    for p in aligned_pairs:
        p["band"] = band_nr
        p["confidence"] = pair["confidence"]

    return aligned_pairs


def main() -> None:
    print("\n=== Phase 4: Sentence-Alignment ===\n")
    state = load_state()

    if not state.get("bertalign_available", True):
        halt(
            "bertalign nicht verfügbar.\n"
            "Fix: cd app/backend && uv pip install bertalign\n"
            "Danach: python scripts/shuukura_rag/phase_00_inspect.py erneut ausführen"
        )

    matched_pairs = state.get("matched_pairs", [])
    if not matched_pairs:
        halt("matched_pairs fehlt in state.json — Phase 3 zuerst ausführen.")

    all_stats: list[dict] = []
    aligned_files: list[str] = []
    report_rows: list[str] = []

    for pair in matched_pairs:
        band_nr = pair["jp_band"]
        out_file = STAGING_DIR / f"aligned_band_{band_nr:02d}.jsonl"

        # Idempotenz: bereits alignierte Bände überspringen
        if out_file.exists():
            existing_count = len(out_file.read_text(encoding="utf-8").strip().splitlines())
            print(f"  Band {band_nr:02d}: bereits aligniert ({existing_count} Pairs) — überspringe.")
            aligned_files.append(str(out_file))
            all_stats.append({"band": band_nr, "pairs": existing_count, "confidence": pair["confidence"]})
            report_rows.append(
                f"| {band_nr:02d} | {existing_count} | {pair['confidence']} | (bereits fertig) |"
            )
            continue

        print(f"\nBand {band_nr:02d} ({pair['confidence']}):", flush=True)
        aligned_pairs = align_band_pair(pair)

        with out_file.open("w", encoding="utf-8") as f:
            for p in aligned_pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

        aligned_files.append(str(out_file))

        count = len(aligned_pairs)
        avg_jp = sum(len(p["jp"]) for p in aligned_pairs) / count if count else 0
        avg_en = sum(len(p["en"]) for p in aligned_pairs) / count if count else 0
        all_stats.append({
            "band": band_nr,
            "pairs": count,
            "confidence": pair["confidence"],
        })
        report_rows.append(
            f"| {band_nr:02d} | {count} | {pair['confidence']} "
            f"| Ø {avg_jp:.0f} chars JP / {avg_en:.0f} chars EN |"
        )

    save_state({"aligned_files": aligned_files, "alignment_stats": all_stats})

    total_pairs = sum(s["pairs"] for s in all_stats)
    write_report("04_alignment.md", f"""# Phase 4: Sentence-Alignment

| Band | Pairs | Confidence | Avg Laenge |
|---|---|---|---|
{chr(10).join(report_rows)}

**Total aligned Pairs: {total_pairs}**

## Hinweise
- Baende 1+2: WN<->LN — qualitativ schlechter als LN<->LN
- Sehr kurze Pairs (<5 Zeichen) koennen Rauschen sein
- Alignment ist idempotent — erneutes Ausfuehren ueberspringt fertige Baende
""")
    print(f"\n[OK] Phase 4 abgeschlossen. Total: {total_pairs} Pairs.")


if __name__ == "__main__":
    main()
