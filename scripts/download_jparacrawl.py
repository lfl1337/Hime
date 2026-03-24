"""
Hime - JParaCrawl v3.0 Downloader
Lädt den JP/EN Parallel-Corpus herunter und bereitet ihn vor.
"""

import os
import gzip
import shutil
from pathlib import Path
from tqdm import tqdm
import pandas as pd

# ── Konfiguration ─────────────────────────────────────────────
PROJECT_ROOT = Path(r"C:\Projekte\Hime")
RAW_DIR      = PROJECT_ROOT / "data" / "raw_jparacrawl"
ALIGNED_DIR  = PROJECT_ROOT / "data" / "aligned"
TRAINING_DIR = PROJECT_ROOT / "data" / "training"

for d in [RAW_DIR, ALIGNED_DIR, TRAINING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# JParaCrawl v3.0 URLs
URLS = {
    "small": {
        "url": "http://www.kecl.ntt.co.jp/icl/lirg/jparacrawl/release/3.0/bitext/en-ja.tar.gz",
        "filename": "en-ja.tar.gz",
        "size": "~3.8GB"
    }
}

def download_file(url: str, dest: Path):
    """Download mit Fortschrittsanzeige."""
    print(f"\n[..] Downloade: {url}")
    print(f"     Ziel: {dest}")

    response = requests.get(url, stream=True)
    total = int(response.headers.get("content-length", 0))

    with open(dest, "wb") as f, tqdm(
        total=total,
        unit="iB",
        unit_scale=True,
        unit_divisor=1024,
        desc=dest.name
    ) as bar:
        for chunk in response.iter_content(chunk_size=8192):
            size = f.write(chunk)
            bar.update(size)

    print(f"[OK] Download abgeschlossen: {dest}")


def extract_archive(archive: Path, dest_dir: Path):
    """Entpackt tar.gz Archiv."""
    print(f"\n[..] Entpacke {archive.name} ...")
    shutil.unpack_archive(str(archive), str(dest_dir))
    print(f"[OK] Entpackt nach {dest_dir}")


def prepare_training_data_bitext(bitext_file: Path, output_file: Path, max_pairs: int = 500_000):
    """
    Konvertiert JParaCrawl v3.0 Bitext-Datei (tab-separiert: EN\tJA) in JSONL Trainingsformat.
    Format: {"instruction": "...", "input": "JP Text", "output": "EN Text"}
    """
    print(f"\n[..] Bereite Trainingsdaten vor aus: {bitext_file.name}")
    print(f"     Max {max_pairs:,} Paare ...")

    INSTRUCTION = (
        "Translate the following Japanese light novel text to English. "
        "Preserve the tone, honorifics, and narrative style."
    )

    count = 0
    skipped = 0

    import json

    with open(bitext_file, "r", encoding="utf-8") as f, \
         open(output_file, "w", encoding="utf-8") as out_f:

        for line in tqdm(f, total=max_pairs, desc="Paare verarbeiten"):
            line = line.rstrip("\n")

            # Tab-separiertes Format: EN \t JA
            parts = line.split("\t")
            if len(parts) < 2:
                skipped += 1
                continue

            en = parts[0].strip()
            jp = parts[1].strip()

            # Qualitätsfilter
            if not jp or not en:
                skipped += 1
                continue
            if len(jp) < 5 or len(en) < 5:
                skipped += 1
                continue
            if len(jp) > 2000 or len(en) > 2000:
                skipped += 1
                continue
            # Mindestens 1 japanisches Zeichen
            if not any('\u3000' <= c <= '\u9fff' for c in jp):
                skipped += 1
                continue

            entry = {
                "instruction": INSTRUCTION,
                "input": jp,
                "output": en
            }
            out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1

            if count >= max_pairs:
                break

    print(f"[OK] {count:,} Trainingspaare gespeichert → {output_file}")
    print(f"     {skipped:,} Paare übersprungen (zu kurz/lang/leer/kein JP)")
    return count


def main():
    print("=" * 60)
    print("  Hime - JParaCrawl v3.0 Downloader")
    print("=" * 60)

    # Schritt 1: Download
    archive_path = RAW_DIR / "en-ja.tar.gz"

    if archive_path.exists():
        print(f"\n[OK] Archiv bereits vorhanden: {archive_path}")
    else:
        download_file(URLS["small"]["url"], archive_path)

    # Schritt 2: Entpacken
    extract_dir = RAW_DIR / "extracted"
    extract_dir.mkdir(exist_ok=True)

    if not any(extract_dir.iterdir()):
        extract_archive(archive_path, extract_dir)
    else:
        print(f"[OK] Bereits entpackt: {extract_dir}")

    # Schritt 3: Bitext-Datei finden (JParaCrawl v3.0 Format: EN\tJA in einer Datei)
    print("\n[..] Suche Bitext-Datei ...")
    bitext_candidates = (
        list(extract_dir.rglob("*.bicleaner05.txt")) +
        list(extract_dir.rglob("*.txt")) +
        list(extract_dir.rglob("en-ja*"))
    )
    # Nur echte Dateien (keine Verzeichnisse)
    bitext_candidates = [f for f in bitext_candidates if f.is_file()]

    if not bitext_candidates:
        print("[!] Keine Bitext-Datei gefunden. Inhalt von extracted:")
        for f in extract_dir.rglob("*"):
            print(f"    {f}")
        return

    bitext_file = bitext_candidates[0]
    print(f"[OK] Bitext-Datei: {bitext_file}")

    # Schritt 4: Trainingsdaten erstellen
    output_file = TRAINING_DIR / "jparacrawl_500k.jsonl"
    count = prepare_training_data_bitext(bitext_file, output_file, max_pairs=500_000)

    print("\n" + "=" * 60)
    print(f"  Fertig! {count:,} Trainingspaare bereit.")
    print(f"  Datei: {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()