"""
Hime - EPUB Extraktor v2
Korrekte Furigana-Behandlung für Bookwalker/Kadokawa EPUBs.
Serie: 声優ラジオのウラオモテ
"""

import zipfile
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm import tqdm

# ── Konfiguration ─────────────────────────────────────────────
PROJECT_ROOT = Path(r"C:\Projekte\Hime")
EPUB_DIR     = PROJECT_ROOT / "data" / "epubs"
RAW_JP_DIR   = PROJECT_ROOT / "data" / "raw_jp"
TRAINING_DIR = PROJECT_ROOT / "data" / "training"

for d in [EPUB_DIR, RAW_JP_DIR, TRAINING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Seiten die übersprungen werden sollen
SKIP_PAGES = [
    'cover', 'titlepage', 'colophon', 'bookwalker',
    'caution', 'allcover', 'fmatter', 'bmatter', 'toc',
    'navigation'
]


def clean_furigana(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Entfernt Furigana (rt Tags) korrekt.
    Behält den Basistext (rb oder direkte Text-Nodes in ruby).
    """
    for ruby in soup.find_all('ruby'):
        # rt (Furigana-Lesung) entfernen
        for rt in ruby.find_all('rt'):
            rt.decompose()
        # rp (Klammern) entfernen
        for rp in ruby.find_all('rp'):
            rp.decompose()
        # rb Text extrahieren und ruby-Tag ersetzen
        base_text = ruby.get_text()
        ruby.replace_with(base_text)
    return soup


def extract_page_text(xhtml_content: str) -> str:
    """Extrahiert sauberen Text aus einer XHTML Seite."""
    soup = BeautifulSoup(xhtml_content, 'html.parser')

    # Furigana korrekt entfernen
    soup = clean_furigana(soup)

    body = soup.find('body')
    if not body:
        return ""

    # Alle Paragraphen und Divs mit Text sammeln
    texts = []

    for elem in body.find_all(['p', 'div', 'h1', 'h2', 'h3', 'span']):
        # Nur direkte Text-Elemente, keine geschachtelten
        if elem.find(['p', 'div']):
            continue

        text = elem.get_text().strip()

        # Leerzeichen normalisieren
        text = re.sub(r'[ \t　]+', ' ', text)
        text = text.strip()

        if text and len(text) > 1:
            texts.append(text)

    # Zusammenführen
    result = '\n'.join(texts)

    # Titel-Zeile (wird auf jeder Seite wiederholt) entfernen
    lines = result.split('\n')
    if lines and len(lines[0]) < 60:
        lines = lines[1:]  # Erste Zeile (Titel) entfernen

    # Doppelte Leerzeilen entfernen
    result = '\n'.join(lines)
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()


def extract_epub(epub_path: Path) -> dict:
    """Extrahiert alle Texte aus einer EPUB Datei."""
    result = {
        "title": epub_path.stem,
        "language": "ja",
        "sections": []
    }

    with zipfile.ZipFile(epub_path, 'r') as z:
        # Metadaten
        try:
            opf_files = [f for f in z.namelist() if f.endswith('.opf')]
            if opf_files:
                opf_content = z.read(opf_files[0]).decode('utf-8')
                # Einfacher Regex statt lxml
                title_match = re.search(r'<dc:title[^>]*>([^<]+)</dc:title>', opf_content)
                lang_match  = re.search(r'<dc:language[^>]*>([^<]+)</dc:language>', opf_content)
                if title_match:
                    result["title"] = title_match.group(1).strip()
                if lang_match:
                    result["language"] = lang_match.group(1).strip()
        except Exception as e:
            pass

        # Alle XHTML Seiten sortiert
        xhtml_files = sorted([
            f for f in z.namelist()
            if f.endswith('.xhtml') and '/xhtml/' in f
            and not any(skip in f.lower() for skip in SKIP_PAGES)
        ])

        for xhtml_file in xhtml_files:
            try:
                content = z.read(xhtml_file).decode('utf-8')
                text = extract_page_text(content)

                if text and len(text) > 200:  # Mindestens 200 Zeichen
                    result["sections"].append({
                        "page": xhtml_file.split('/')[-1],
                        "text": text,
                        "length": len(text)
                    })
            except Exception as e:
                continue

    return result


def split_into_chunks(text: str, chunk_size: int = 1500) -> list:
    """Teilt langen Text in Chunks für das Training."""
    # An Absätzen trennen
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > chunk_size and current:
            chunks.append('\n\n'.join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append('\n\n'.join(current))

    return [c for c in chunks if len(c) > 100]


def process_all_epubs():
    """Verarbeitet alle EPUBs und erstellt Trainingsdaten."""
    epub_files = sorted(EPUB_DIR.glob("*.epub"))

    if not epub_files:
        print(f"[!] Keine EPUBs in {EPUB_DIR}")
        print(f"    Bitte EPUBs dort reinkopieren!")
        return

    print(f"[OK] {len(epub_files)} EPUBs gefunden\n")

    INSTRUCTION = (
        "Translate the following Japanese light novel text to English. "
        "This is from 'Seiyuu Radio no Uraomote', a yuri light novel. "
        "Preserve the tone, character voices, honorifics, and the emotional nuance between characters."
    )

    all_entries = []
    total_chars = 0

    for epub_path in epub_files:
        print(f"[..] {epub_path.name}")

        result = extract_epub(epub_path)
        print(f"     Titel:    {result['title']}")
        print(f"     Sprache:  {result['language']}")
        print(f"     Seiten:   {len(result['sections'])} mit Text")

        # Text pro Sektion speichern
        vol_num = re.sub(r'[^0-9]', '', epub_path.stem).zfill(2)
        novel_name = f"SeiyuuRadio_Vol{vol_num}"
        save_dir = RAW_JP_DIR / novel_name
        save_dir.mkdir(exist_ok=True)

        chunk_count = 0
        vol_chars = 0

        for section in result["sections"]:
            # Große Seiten in Chunks aufteilen
            chunks = split_into_chunks(section["text"], chunk_size=2000)

            for chunk in chunks:
                save_path = save_dir / f"chunk_{str(chunk_count).zfill(4)}.txt"
                save_path.write_text(chunk, encoding="utf-8")

                entry = {
                    "instruction": INSTRUCTION,
                    "input": chunk,
                    "output": "",
                    "source": result["title"],
                    "volume": vol_num,
                    "chunk": chunk_count,
                    "status": "needs_translation"
                }
                all_entries.append(entry)
                chunk_count += 1
                vol_chars += len(chunk)

        total_chars += vol_chars
        print(f"     Chunks:   {chunk_count} (~{vol_chars:,} Zeichen)")
        print()

    # Alles als eine JSONL speichern
    output_file = TRAINING_DIR / "seiyuu_radio_all_jp.jsonl"
    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print("=" * 60)
    print(f"  Fertig!")
    print(f"  Gesamt Chunks:    {len(all_entries)}")
    print(f"  Gesamt Zeichen:   {total_chars:,}")
    print(f"  Output:           {output_file}")
    print("=" * 60)

    # Kurzer Preview
    if all_entries:
        print(f"\nPreview erster Chunk:")
        print("-" * 40)
        print(all_entries[0]["input"][:300])
        print("...")


if __name__ == "__main__":
    process_all_epubs()
