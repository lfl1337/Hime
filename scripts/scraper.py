"""
Hime - Syosetu (JP) + Baka-Tsuki (EN) Scraper
Lädt japanische Originale von Syosetu und englische Übersetzungen
von Baka-Tsuki herunter und erstellt Trainingspaare.
"""

import json
import os
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm import tqdm

# ── Konfiguration ─────────────────────────────────────────────
PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)
RAW_JP_DIR   = PROJECT_ROOT / "data" / "raw_jp"
RAW_EN_DIR   = PROJECT_ROOT / "data" / "raw_en"
TRAINING_DIR = PROJECT_ROOT / "data" / "training"

for d in [RAW_JP_DIR, RAW_EN_DIR, TRAINING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
DELAY = 2.0

# ── Novel-Paare mit korrekten IDs ─────────────────────────────
NOVEL_PAIRS = [
    {
        "title": "Overlord",
        "syosetu_id": "n4402bd",
        "baka_tsuki_url": "https://www.baka-tsuki.org/project/index.php?title=Overlord_(LN)",
    },
    {
        "title": "Mushoku_Tensei",
        "syosetu_id": "s5750d",
        "baka_tsuki_url": "https://www.baka-tsuki.org/project/index.php?title=Mushoku_Tensei",
    },
    {
        "title": "ReZero",
        "syosetu_id": "n2267be",
        "baka_tsuki_url": "https://www.baka-tsuki.org/project/index.php?title=Re:Zero_kara_Hajimeru_Isekai_Seikatsu",
    },
    {
        "title": "Sword_Art_Online",
        "syosetu_id": None,
        "baka_tsuki_url": "https://www.baka-tsuki.org/project/index.php?title=Sword_Art_Online",
    },
]


# ══════════════════════════════════════════════════════════════
#  SYOSETU SCRAPER (Japanisch)
# ══════════════════════════════════════════════════════════════

def get_syosetu_chapter_list(novel_id: str) -> list:
    url = f"https://ncode.syosetu.com/{novel_id}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Fehler Kapitelliste: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    chapters = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if f"/{novel_id}/" in href:
            parts = href.strip("/").split("/")
            if len(parts) >= 2 and parts[-1].isdigit():
                chapters.append({
                    "num": parts[-1],
                    "title": a.text.strip(),
                    "url": f"https://ncode.syosetu.com{href}"
                })

    # Duplikate entfernen
    seen = set()
    unique = []
    for c in chapters:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)

    print(f"[OK] {len(unique)} JP Kapitel gefunden")
    return unique


def scrape_syosetu_chapter(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Fehler: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.find("div", id="novel_honbun") or soup.find("div", class_="novel_view")
    if not content:
        return ""

    return "\n".join(p.get_text().strip() for p in content.find_all("p") if p.get_text().strip())


def scrape_syosetu_novel(novel_id: str, title: str, max_chapters: int = 50):
    print(f"\n[..] Syosetu JP: {title} ({novel_id})")
    save_dir = RAW_JP_DIR / title
    save_dir.mkdir(exist_ok=True)

    chapters = get_syosetu_chapter_list(novel_id)[:max_chapters]
    if not chapters:
        print(f"[!] Keine Kapitel gefunden")
        return

    for chap in tqdm(chapters, desc=f"JP {title}"):
        save_path = save_dir / f"chapter_{chap['num'].zfill(4)}.txt"
        if save_path.exists():
            continue
        text = scrape_syosetu_chapter(chap["url"])
        if text:
            save_path.write_text(text, encoding="utf-8")
        time.sleep(DELAY)

    print(f"[OK] Gespeichert → {save_dir}")


# ══════════════════════════════════════════════════════════════
#  BAKA-TSUKI SCRAPER (Englisch)
# ══════════════════════════════════════════════════════════════

def get_baka_tsuki_chapter_links(index_url: str) -> list:
    try:
        resp = requests.get(index_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Baka-Tsuki Fehler: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.find("div", id="mw-content-text")
    if not content:
        return []

    chapters = []
    seen = set()
    keywords = ["Chapter", "Volume", "Prologue", "Epilogue", "Interlude", "Afterword"]

    for a in content.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()
        if "/project/index.php?title=" in href and any(kw in text for kw in keywords):
            full_url = f"https://www.baka-tsuki.org{href}"
            if full_url not in seen:
                seen.add(full_url)
                chapters.append({"title": text, "url": full_url})

    print(f"[OK] {len(chapters)} EN Kapitel gefunden")
    return chapters


def scrape_baka_tsuki_chapter(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Fehler: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.find("div", id="mw-content-text")
    if not content:
        return ""

    for tag in content.find_all(["table", "div"], class_=["toc", "navbox", "noprint"]):
        tag.decompose()

    return "\n\n".join(
        p.get_text().strip() for p in content.find_all("p")
        if len(p.get_text().strip()) > 20
    )


def scrape_baka_tsuki_novel(index_url: str, title: str, max_chapters: int = 50):
    print(f"\n[..] Baka-Tsuki EN: {title}")
    save_dir = RAW_EN_DIR / title
    save_dir.mkdir(exist_ok=True)

    chapters = get_baka_tsuki_chapter_links(index_url)[:max_chapters]
    if not chapters:
        print(f"[!] Keine Kapitel gefunden")
        return

    for i, chap in enumerate(tqdm(chapters, desc=f"EN {title}")):
        save_path = save_dir / f"chapter_{str(i+1).zfill(4)}.txt"
        if save_path.exists():
            continue
        text = scrape_baka_tsuki_chapter(chap["url"])
        if text:
            save_path.write_text(text, encoding="utf-8")
        time.sleep(DELAY)

    print(f"[OK] Gespeichert → {save_dir}")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Hime - Syosetu + Baka-Tsuki Scraper")
    print("=" * 60)

    for novel in NOVEL_PAIRS:
        title = novel["title"]
        print(f"\n{'─' * 40}")
        print(f"  Novel: {title}")
        print(f"{'─' * 40}")

        if novel.get("syosetu_id"):
            try:
                scrape_syosetu_novel(novel["syosetu_id"], title, max_chapters=50)
            except Exception as e:
                print(f"[!] Syosetu Fehler: {e}")
        else:
            print(f"[i] Kein Syosetu verfügbar, überspringe JP")

        try:
            scrape_baka_tsuki_novel(novel["baka_tsuki_url"], title, max_chapters=50)
        except Exception as e:
            print(f"[!] Baka-Tsuki Fehler: {e}")

        time.sleep(3)

    print("\n" + "=" * 60)
    print("  Scraping abgeschlossen!")
    print(f"  JP: {RAW_JP_DIR}")
    print(f"  EN: {RAW_EN_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
