"""
Hime - JParaCrawl Konverter (angepasst ans echte Format)
Format: domain\tdomain\tscore\ten_text\tjp_text
"""

import json
from pathlib import Path
from tqdm import tqdm

# ── Konfiguration ─────────────────────────────────────────────
PROJECT_ROOT = Path(r"C:\Projekte\Hime")
INPUT_FILE   = PROJECT_ROOT / "data" / "raw_jparacrawl" / "extracted" / "en-ja" / "en-ja.bicleaner05.txt"
TRAINING_DIR = PROJECT_ROOT / "data" / "training"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE  = TRAINING_DIR / "jparacrawl_500k.jsonl"

# Mindest-Score für Qualität (0.0 - 1.0)
MIN_SCORE    = 0.7
MAX_PAIRS    = 500_000

INSTRUCTION = (
    "Translate the following Japanese text to English. "
    "Preserve the tone, meaning, and style of the original."
)

def main():
    print("=" * 60)
    print("  Hime - JParaCrawl Konverter")
    print("=" * 60)
    print(f"\n[..] Lese: {INPUT_FILE}")
    print(f"     Min-Score: {MIN_SCORE}")
    print(f"     Max Paare: {MAX_PAIRS:,}")

    count    = 0
    skipped  = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as f_in, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as f_out:

        for line in tqdm(f_in, desc="Verarbeite Paare"):
            parts = line.rstrip("\n").split("\t")

            # Format: domain, domain, score, en, jp
            if len(parts) != 5:
                skipped += 1
                continue

            _, _, score_str, en_text, jp_text = parts

            # Score filtern
            try:
                score = float(score_str)
            except ValueError:
                skipped += 1
                continue

            if score < MIN_SCORE:
                skipped += 1
                continue

            en_text = en_text.strip()
            jp_text = jp_text.strip()

            # Qualitätsfilter
            if not en_text or not jp_text:
                skipped += 1
                continue
            if len(jp_text) < 5 or len(en_text) < 5:
                skipped += 1
                continue
            if len(jp_text) > 1000 or len(en_text) > 1000:
                skipped += 1
                continue
            # Mindestens ein japanisches Zeichen
            if not any('\u3000' <= c <= '\u9fff' for c in jp_text):
                skipped += 1
                continue

            entry = {
                "instruction": INSTRUCTION,
                "input": jp_text,
                "output": en_text,
                "score": score
            }
            f_out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1

            if count >= MAX_PAIRS:
                print(f"\n[OK] Maximum von {MAX_PAIRS:,} Paaren erreicht.")
                break

    print("\n" + "=" * 60)
    print(f"  Fertig!")
    print(f"  Gespeicherte Paare:    {count:,}")
    print(f"  Übersprungene Paare:   {skipped:,}")
    print(f"  Output: {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
