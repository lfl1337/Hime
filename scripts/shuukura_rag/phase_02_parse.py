# scripts/shuukura_rag/phase_02_parse.py
"""
Phase 2: Alle EPUBs (JP + EN) in strukturierte JSON-Staging-Dateien parsen.

Output-Format pro Band (z.B. shuukura_jp_01.json):
{
  "lang": "jp",
  "band": 1,
  "source_file": "...",
  "chapters": [
    {
      "title": "...",
      "paragraphs": [
        {"raw": "...", "sentences": ["...", "..."]}
      ]
    }
  ]
}

Erzeugt: data/rag/staging/shuukura/shuukura_jp_01.json .. shuukura_en_07.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Windows-Konsole: UTF-8 erzwingen
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import STAGING_DIR, halt, load_state, save_state, write_report


def segment_jp(text: str) -> list[str]:
    """JP-Satz-Splitter: nach 。！？ splitten."""
    sentences = re.split(r"(?<=[。！？])\s*", text)
    return [s.strip() for s in sentences if s.strip()]


def segment_en(text: str) -> list[str]:
    """EN-Satz-Splitter: nach . ! ? + Großbuchstabe."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", text)
    return [s.strip() for s in sentences if s.strip()]


def parse_epub(path: Path, lang: str, band_nr: int) -> dict:
    """Parst ein EPUB in die Staging-Datenstruktur."""
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    segmenter = segment_jp if lang == "jp" else segment_en

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        raw_blocks = []
        for tag in soup.find_all(["p", "div"]):
            text = tag.get_text(separator=" ").strip()
            if text:
                raw_blocks.append(text)

        if not raw_blocks:
            continue

        paragraphs = []
        for block in raw_blocks:
            sents = segmenter(block)
            if sents:
                paragraphs.append({"raw": block, "sentences": sents})

        if paragraphs:
            title = raw_blocks[0][:80] if raw_blocks else item.get_id()
            chapters.append({"title": title, "paragraphs": paragraphs})

    return {
        "lang": lang,
        "band": band_nr,
        "source_file": path.name,
        "chapters": chapters,
    }


def is_bonus_content(path: Path) -> bool:
    """Erkennt Bonus-/Sondermaterial das kein regulärer Band ist."""
    name = path.name
    # 購入特典 = Store-Kaufbonus-Short-Story
    if "購入特典" in name:
        return True
    return False


def extract_band_number(path: Path) -> int:
    """Extrahiert die Bandnummer aus einem Dateinamen."""
    name = path.stem
    # Muster: 話 + Zahl (JP: 週に一度...話5, 話２ etc.)
    m = re.search(r"話\s*([0-9０-９]+)", name)
    if m:
        num_str = m.group(1)
        # Fullwidth digits -> ASCII
        num_str = num_str.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        return int(num_str)
    # Muster: 第01, 第02 (JP-typisch)
    m = re.search(r"第0?(\d{1,2})", name)
    if m:
        return int(m.group(1))
    # Muster: 話 ohne Zahl = Band 1 (Erstband oft ohne Nummer)
    if "週に一度クラスメイトを買う話" in name and not re.search(r"[0-9０-９]", name):
        return 1
    # Muster: _01_, _02_ (underscore-separated)
    m = re.search(r"[_\-\s]0?(\d{1,2})[_\-\s\.]", name)
    if m:
        return int(m.group(1))
    # Muster: Volume 5, Vol. 2
    m = re.search(r"[Vv]ol(?:ume)?\.?\s*(\d+)", name)
    if m:
        return int(m.group(1))
    # Muster: WN-Band via Teile (Parts 1-34 -> Vol 1)
    if "Vol. 1" in path.name or "Vol.1" in path.name or "WN Vol. 1" in path.name:
        return 1
    if "Vol. 2" in path.name or "Vol.2" in path.name or "WN Vol. 2" in path.name:
        return 2
    # Letzter Ausweg: erste Zahl im Dateinamen
    m = re.search(r"(\d+)", name)
    return int(m.group(1)) if m else 0


def stats(data: dict) -> tuple[int, int, int]:
    """Gibt (chapters, paragraphs, sentences) zurück."""
    ch = len(data["chapters"])
    pa = sum(len(c["paragraphs"]) for c in data["chapters"])
    se = sum(len(p["sentences"]) for c in data["chapters"] for p in c["paragraphs"])
    return ch, pa, se


def main() -> None:
    print("\n=== Phase 2: EPUB-Parsing ===\n")
    state = load_state()

    jp_epubs = [Path(p) for p in state.get("jp_epubs", [])]
    en_epubs = [Path(p) for p in state.get("en_epubs", [])]

    if not jp_epubs or not en_epubs:
        halt("Keine EPUB-Pfade in state.json — Phase 1 zuerst ausführen.")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    parsed_jp: list[str] = []
    parsed_en: list[str] = []
    report_rows: list[str] = []

    # JP parsen
    print("-- JP-Bände --")
    for epub_path in sorted(jp_epubs):
        if is_bonus_content(epub_path):
            print(f"  UEBERSPRUNGEN (Bonus/Sondermaterial): {epub_path.name[:60]}")
            continue
        band_nr = extract_band_number(epub_path)
        if band_nr == 0:
            print(f"  UEBERSPRUNGEN (Bandnummer nicht erkannt): {epub_path.name}")
            continue
        print(f"  Band {band_nr:02d}: {epub_path.name[:60]} ...", end=" ", flush=True)
        data = parse_epub(epub_path, "jp", band_nr)
        ch, pa, se = stats(data)
        print(f"{ch} Kap, {pa} Para, {se} Saetze")

        out = STAGING_DIR / f"shuukura_jp_{band_nr:02d}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        parsed_jp.append(str(out))

        sample = ""
        if data["chapters"] and data["chapters"][0]["paragraphs"]:
            sample = data["chapters"][0]["paragraphs"][0]["raw"][:60]
        report_rows.append(
            f"| JP {band_nr:02d} | {ch} | {pa} | {se} | {repr(sample[:40])} |"
        )

    # EN parsen
    print("\n-- EN-Bände --")
    for epub_path in sorted(en_epubs):
        band_nr = extract_band_number(epub_path)
        if band_nr == 0:
            print(f"  UEBERSPRUNGEN (Bandnummer nicht erkannt): {epub_path.name}")
            continue
        print(f"  Band {band_nr:02d}: {epub_path.name[:60]} ...", end=" ", flush=True)
        data = parse_epub(epub_path, "en", band_nr)
        ch, pa, se = stats(data)
        print(f"{ch} Kap, {pa} Para, {se} Saetze")

        out = STAGING_DIR / f"shuukura_en_{band_nr:02d}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        parsed_en.append(str(out))

        sample = ""
        if data["chapters"] and data["chapters"][0]["paragraphs"]:
            sample = data["chapters"][0]["paragraphs"][0]["raw"][:60]
        report_rows.append(
            f"| EN {band_nr:02d} | {ch} | {pa} | {se} | {repr(sample[:40])} |"
        )

    save_state({"parsed_jp": parsed_jp, "parsed_en": parsed_en})

    write_report("02_parsing.md", f"""# Phase 2: EPUB-Parsing

| Band | Kapitel | Paragraphen | Saetze | Sample |
|---|---|---|---|---|
{chr(10).join(report_rows)}

**JP gesamt: {len(parsed_jp)} Baende**
**EN gesamt: {len(parsed_en)} Baende**
""")
    print(f"\n[OK] Phase 2 abgeschlossen. JP: {len(parsed_jp)}, EN: {len(parsed_en)} Baende.")


if __name__ == "__main__":
    main()
