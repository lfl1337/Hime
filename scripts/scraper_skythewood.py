"""
Hime - Skythewood Scraper (Overlord EN)
Scrapt englische Übersetzungen von skythewood.blogspot.com
und pairt sie mit den bereits gescrapten JP Kapiteln von Syosetu.
"""

import json
import os
import time
import re
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm import tqdm

# ── Konfiguration ─────────────────────────────────────────────
PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)
RAW_EN_DIR   = PROJECT_ROOT / "data" / "raw_en"
RAW_JP_DIR   = PROJECT_ROOT / "data" / "raw_jp"
TRAINING_DIR = PROJECT_ROOT / "data" / "training"

for d in [RAW_EN_DIR, TRAINING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
DELAY = 2.0

# ── Skythewood Overlord Kapitel-URLs ──────────────────────────
# Format: Volume -> Liste von Part-URLs
# Skythewood nutzt URLs wie: skythewood.blogspot.com/YYYY/MM/O{Vol}{Chap}{Part}.html

OVERLORD_INDEX_URL = "http://skythewood.blogspot.com/p/overlord-2.html"


def get_skythewood_overlord_chapters() -> list:
    """Holt alle Kapitel-Links von der Overlord Index-Seite."""
    print(f"[..] Lade Skythewood Overlord Index ...")
    try:
        resp = requests.get(OVERLORD_INDEX_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Fehler: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    chapters = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()

        # Nur Skythewood Blog Links
        if "skythewood.blogspot.com" in href or href.startswith("/"):
            if any(kw in text for kw in ["Prologue", "Chapter", "Epilogue", "Intermission", "Part"]):
                if href not in seen:
                    seen.add(href)
                    chapters.append({"title": text, "url": href})

    print(f"[OK] {len(chapters)} Links gefunden")
    return chapters


def scrape_skythewood_chapter(url: str) -> str:
    """Scrapt den Text eines Skythewood Kapitels."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Fehler {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Blogpost Inhalt
    content = (
        soup.find("div", class_="post-body") or
        soup.find("div", class_="entry-content") or
        soup.find("article")
    )

    if not content:
        return ""

    # Navigations-Links und Kommentare entfernen
    for tag in content.find_all(["script", "style", "nav"]):
        tag.decompose()

    paragraphs = []
    for p in content.find_all("p"):
        text = p.get_text().strip()
        if text and len(text) > 20:
            # Typische Navigations-Texte überspringen
            skip_phrases = ["Previous Chapter", "Next Chapter", "Table of Contents",
                          "Click here", "Support us", "Donate", "Translator"]
            if not any(phrase.lower() in text.lower() for phrase in skip_phrases):
                paragraphs.append(text)

    return "\n\n".join(paragraphs)


def scrape_skythewood_overlord(max_chapters: int = 60):
    """Scrapt Overlord EN von Skythewood."""
    print(f"\n{'─' * 40}")
    print(f"  Skythewood: Overlord EN")
    print(f"{'─' * 40}")

    save_dir = RAW_EN_DIR / "Overlord"
    save_dir.mkdir(exist_ok=True)

    chapters = get_skythewood_overlord_chapters()
    if not chapters:
        print("[!] Keine Kapitel gefunden auf Index-Seite")
        print("[i] Versuche direkten Zugriff auf bekannte URLs ...")
        chapters = get_overlord_direct_urls()

    chapters = chapters[:max_chapters]
    saved = 0

    for i, chap in enumerate(tqdm(chapters, desc="EN Overlord")):
        save_path = save_dir / f"chapter_{str(i+1).zfill(4)}.txt"

        if save_path.exists():
            saved += 1
            continue

        text = scrape_skythewood_chapter(chap["url"])
        if text:
            save_path.write_text(text, encoding="utf-8")
            saved += 1

        time.sleep(DELAY)

    print(f"[OK] {saved} EN Kapitel gespeichert → {save_dir}")
    return saved


def get_overlord_direct_urls() -> list:
    """
    Fallback: Bekannte direkte URLs für Overlord Kapitel.
    Skythewood URL-Muster: O{Volume}{Chapter}{Part}
    """
    chapters = []

    # Volume 1
    vol1 = [
        ("http://skythewood.blogspot.com/2014/10/O11.html", "Vol1 Prologue/Ch1 Part1"),
        ("http://skythewood.blogspot.com/2014/10/O12.html", "Vol1 Ch1 Part2"),
        ("http://skythewood.blogspot.com/2014/10/O13.html", "Vol1 Ch1 Part3"),
        ("http://skythewood.blogspot.com/2014/11/O21.html", "Vol1 Ch2 Part1"),
        ("http://skythewood.blogspot.com/2014/11/O22.html", "Vol1 Ch2 Part2"),
        ("http://skythewood.blogspot.com/2014/11/O23.html", "Vol1 Ch2 Part3"),
        ("http://skythewood.blogspot.com/2014/11/O31.html", "Vol1 Ch3 Part1"),
        ("http://skythewood.blogspot.com/2014/11/O32.html", "Vol1 Ch3 Part2"),
        ("http://skythewood.blogspot.com/2014/12/O33.html", "Vol1 Ch3 Part3"),
        ("http://skythewood.blogspot.com/2014/12/O41a.html", "Vol1 Ch4 Part1"),
    ]

    # Volume 2
    vol2 = [
        ("http://skythewood.blogspot.com/2015/01/O2P1.html", "Vol2 Prologue"),
        ("http://skythewood.blogspot.com/2015/01/O211.html", "Vol2 Ch1 Part1"),
        ("http://skythewood.blogspot.com/2015/02/O212.html", "Vol2 Ch1 Part2"),
        ("http://skythewood.blogspot.com/2015/02/O221.html", "Vol2 Ch2 Part1"),
        ("http://skythewood.blogspot.com/2015/02/O222.html", "Vol2 Ch2 Part2"),
        ("http://skythewood.blogspot.com/2015/03/O231.html", "Vol2 Ch3 Part1"),
    ]

    for url, title in vol1 + vol2:
        chapters.append({"url": url, "title": title})

    return chapters


# ══════════════════════════════════════════════════════════════
#  RE:ZERO - Witch Cult Translations
# ══════════════════════════════════════════════════════════════

REZERO_SOURCES = [
    {
        "name": "witchculttranslations",
        "index": "https://witchculttranslations.wordpress.com/table-of-contents/"
    }
]

def scrape_rezero_en(max_chapters: int = 30):
    """Scrapt Re:Zero EN von Witch Cult Translations."""
    print(f"\n{'─' * 40}")
    print(f"  Re:Zero EN (Witch Cult Translations)")
    print(f"{'─' * 40}")

    save_dir = RAW_EN_DIR / "ReZero"
    save_dir.mkdir(exist_ok=True)

    index_url = REZERO_SOURCES[0]["index"]

    try:
        resp = requests.get(index_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Fehler beim Index: {e}")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    chapters = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()
        if "witchculttranslations" in href and any(
            kw in text for kw in ["Chapter", "Arc", "Prologue", "Epilogue"]
        ):
            if href not in seen:
                seen.add(href)
                chapters.append({"title": text, "url": href})

    print(f"[OK] {len(chapters)} Re:Zero EN Links gefunden")
    chapters = chapters[:max_chapters]
    saved = 0

    for i, chap in enumerate(tqdm(chapters, desc="EN ReZero")):
        save_path = save_dir / f"chapter_{str(i+1).zfill(4)}.txt"

        if save_path.exists():
            saved += 1
            continue

        text = scrape_skythewood_chapter(chap["url"])  # Gleiche Logik
        if text:
            save_path.write_text(text, encoding="utf-8")
            saved += 1

        time.sleep(DELAY)

    print(f"[OK] {saved} Re:Zero EN Kapitel gespeichert → {save_dir}")
    return saved


# ══════════════════════════════════════════════════════════════
#  TRAINING DATA ERSTELLEN
# ══════════════════════════════════════════════════════════════

def create_training_data(title: str) -> int:
    """Erstellt JSONL Trainingsdaten aus JP + EN Kapiteln."""
    jp_dir = RAW_JP_DIR / title
    en_dir = RAW_EN_DIR / title

    if not jp_dir.exists():
        print(f"[!] Kein JP Ordner für {title}")
        return 0
    if not en_dir.exists():
        print(f"[!] Kein EN Ordner für {title}")
        return 0

    jp_files = sorted(jp_dir.glob("*.txt"))
    en_files = sorted(en_dir.glob("*.txt"))

    if not jp_files or not en_files:
        print(f"[!] Keine Dateien für {title}")
        return 0

    pairs = list(zip(jp_files, en_files))
    output_file = TRAINING_DIR / f"{title.lower()}_training.jsonl"

    INSTRUCTION = (
        "Translate the following Japanese light novel text to English. "
        "Preserve the tone, character voices, honorifics, and narrative style of the original."
    )

    count = 0
    with open(output_file, "w", encoding="utf-8") as f:
        for jp_file, en_file in tqdm(pairs, desc=f"Training {title}"):
            jp_text = jp_file.read_text(encoding="utf-8").strip()
            en_text = en_file.read_text(encoding="utf-8").strip()

            if not jp_text or not en_text:
                continue
            if len(jp_text) < 100 or len(en_text) < 100:
                continue

            entry = {
                "instruction": INSTRUCTION,
                "input": jp_text[:2000],
                "output": en_text[:2000],
                "source": title,
                "chapter": jp_file.stem
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1

    print(f"[OK] {count} Trainingspaare → {output_file}")
    return count


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Hime - Skythewood + WitchCult Scraper")
    print("=" * 60)

    total = 0

    # Overlord EN
    total += scrape_skythewood_overlord(max_chapters=60)

    # Re:Zero EN
    total += scrape_rezero_en(max_chapters=30)

    # Trainingsdaten erstellen
    print(f"\n{'─' * 40}")
    print("  Erstelle Trainingsdaten ...")
    print(f"{'─' * 40}")

    for title in ["Overlord", "ReZero"]:
        create_training_data(title)

    print("\n" + "=" * 60)
    print(f"  Fertig! {total} EN Kapitel gespeichert.")
    print(f"  Trainingsdaten: {TRAINING_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
