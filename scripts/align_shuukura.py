"""
Hime - ShuuKura Alignment Script v2
Alignt NUR Web Novel JP (Kakuyomu) mit Web Novel EN (Ave Lilium WN EPUBs).
LN Volumes (3-7) werden NICHT verwendet da kein JP Pendant vorhanden.

Warum getrennt?
- WN = Web Novel = Kakuyomu JP + Ave Lilium WN EN → passt zusammen ✅
- LN = Light Novel = andere Version, kein freies JP verfügbar ❌
"""

import json, re, zipfile
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm import tqdm

PROJECT_ROOT = Path(r"C:\Projekte\Hime")
RAW_JP_DIR   = PROJECT_ROOT / "data" / "raw_jp" / "ShuuKura"
EPUB_DIR     = PROJECT_ROOT / "data" / "epubs"
TRAINING_DIR = PROJECT_ROOT / "data" / "training"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)

# NUR Web Novel EPUBs verwenden - LN Volumes haben andere Inhalte!
WN_EPUB_KEYWORDS = ["WN", "Parts", "wn", "parts"]

INSTRUCTION = (
    "Translate the following Japanese yuri light novel text to English. "
    "This is from 'Shuu ni Ichido Kurasumeito wo Kau Hanashi' (週に一度クラスメイトを買う話). "
    "Preserve the intimate, slow-burn tone, internal monologues, "
    "and the nuanced relationship between Miyagi and Sendai."
)

SKIP_PAGES = ['cover', 'title', 'toc', 'nav', 'copyright', 'contents', 'afterword']


def extract_part_number(text: str) -> int:
    """Extrahiert Part-Nummer aus EN Text. Gibt -1 zurück wenn keine gefunden."""
    m = re.search(r'\bPart\s+(\d+)\b', text)
    if m:
        return int(m.group(1))
    return -1


def extract_en_wn_parts(epub_path: Path) -> dict:
    """
    Extrahiert EN Parts aus einem Web Novel EPUB.
    Gibt {part_num: text} zurück.
    """
    parts = {}

    with zipfile.ZipFile(epub_path, 'r') as z:
        xhtml_files = sorted([
            f for f in z.namelist()
            if (f.endswith('.xhtml') or f.endswith('.html'))
            and not any(skip in f.lower() for skip in SKIP_PAGES)
        ])

        for xf in xhtml_files:
            content = z.read(xf).decode('utf-8', errors='ignore')
            soup = BeautifulSoup(content, 'html.parser')
            body = soup.find('body')
            if not body:
                continue

            full_text = body.get_text(' ').strip()
            part_num = extract_part_number(full_text)

            if part_num == -1:
                continue

            # Sauberen Text extrahieren
            paragraphs = [
                p.get_text().strip()
                for p in body.find_all('p')
                if len(p.get_text().strip()) > 20
            ]

            # "Unknown" Header entfernen (Ave Lilium EPUB Artefakt)
            paragraphs = [p for p in paragraphs if p != "Unknown"]

            # Kapitel/Part Header Zeile entfernen
            if paragraphs and re.match(r'^(Chapter|Part)\s+\d+', paragraphs[0]):
                paragraphs = paragraphs[1:]

            text = '\n\n'.join(paragraphs)

            if len(text) > 100:
                if part_num in parts:
                    print(f"[!] Duplikat Part {part_num} in {epub_path.name} - überspringe")
                else:
                    parts[part_num] = text

    return parts


def load_jp_episodes() -> dict:
    """
    Lädt JP Episoden von Kakuyomu.
    Episode N entspricht Part N der Web Novel.
    """
    episodes = {}

    if not RAW_JP_DIR.exists():
        print(f"[!] JP Ordner nicht gefunden: {RAW_JP_DIR}")
        return episodes

    for jp_file in sorted(RAW_JP_DIR.glob("ep_*.txt")):
        num_match = re.search(r'ep_(\d+)', jp_file.stem)
        if not num_match:
            continue
        ep_num = int(num_match.group(1))

        text = jp_file.read_text(encoding="utf-8").strip()

        # Titel-Zeile entfernen
        lines = text.split('\n')
        if lines and lines[0].startswith('#'):
            text = '\n'.join(lines[2:]).strip()

        # Mindestlänge prüfen
        if len(text) > 100:
            episodes[ep_num] = text

    return episodes


def validate_pair(jp: str, en: str) -> bool:
    """
    Einfache Validierung ob JP/EN Paar plausibel ist.
    Prüft ob beide Texte echten Inhalt haben.
    """
    if not jp or not en:
        return False
    if len(jp) < 100 or len(en) < 100:
        return False
    # JP sollte japanische Zeichen enthalten
    if not any('\u3000' <= c <= '\u9fff' or '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in jp):
        return False
    # EN sollte lateinische Zeichen enthalten
    if not any('a' <= c.lower() <= 'z' for c in en):
        return False
    return True


def create_aligned_training_data():
    print("=" * 60)
    print("  Hime - ShuuKura WN Alignment v2")
    print("=" * 60)

    # JP Episoden laden
    jp_episodes = load_jp_episodes()
    print(f"[OK] {len(jp_episodes)} JP Episoden geladen (Parts 1-{max(jp_episodes.keys()) if jp_episodes else 0})")

    # NUR WN EPUBs laden
    all_en_parts = {}
    wn_epubs = [
        f for f in sorted(EPUB_DIR.glob("*.epub"))
        if any(kw in f.name for kw in WN_EPUB_KEYWORDS)
    ]

    if not wn_epubs:
        print("[!] Keine WN EPUBs gefunden!")
        print(f"    Suche in: {EPUB_DIR}")
        print(f"    Keywords: {WN_EPUB_KEYWORDS}")
        return

    print(f"\n[OK] {len(wn_epubs)} WN EPUBs gefunden:")
    for f in wn_epubs:
        print(f"     {f.name}")

    for epub_path in wn_epubs:
        print(f"\n[..] Extrahiere {epub_path.name} ...")
        parts = extract_en_wn_parts(epub_path)
        print(f"     {len(parts)} Parts gefunden: {sorted(parts.keys())[:5]}...")
        all_en_parts.update(parts)

    print(f"\n[OK] Gesamt {len(all_en_parts)} EN Parts (Parts {min(all_en_parts.keys())}-{max(all_en_parts.keys())})")

    # Alignment
    aligned = []
    missing_en = []
    missing_jp = []
    invalid = []

    all_nums = sorted(set(list(jp_episodes.keys()) + list(all_en_parts.keys())))

    for num in all_nums:
        jp = jp_episodes.get(num)
        en = all_en_parts.get(num)

        if jp and en:
            if validate_pair(jp, en):
                aligned.append({
                    "instruction": INSTRUCTION,
                    "input": jp[:3000],
                    "output": en[:3000],
                    "source": "ShuuKura_WN",
                    "part": num
                })
            else:
                invalid.append(num)
        elif jp and not en:
            missing_en.append(num)
        elif en and not jp:
            missing_jp.append(num)

    print(f"\n{'─'*40}")
    print(f"  Alignte Paare:    {len(aligned)}")
    print(f"  JP ohne EN:       {len(missing_en)} {missing_en[:5] if missing_en else ''}")
    print(f"  EN ohne JP:       {len(missing_jp)} {missing_jp[:5] if missing_jp else ''}")
    print(f"  Ungültige Paare:  {len(invalid)}")
    print(f"{'─'*40}")

    if not aligned:
        print("\n[!] Keine Paare gefunden! Prüfe ob JP Episoden vorhanden sind.")
        return

    # Preview
    print(f"\nPreview Paar {aligned[0]['part']}:")
    print(f"JP: {aligned[0]['input'][:150]}...")
    print(f"EN: {aligned[0]['output'][:150]}...")

    # Speichern
    output_file = TRAINING_DIR / "shuukura_wn_aligned.jsonl"
    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in aligned:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"\n[OK] Gespeichert → {output_file}")

    # Zusammenführen
    merge_all_training_data(len(aligned))


def merge_all_training_data(shuukura_count: int):
    """Führt alle validen Trainingsdaten zusammen."""
    print(f"\n[..] Führe alle Trainingsdaten zusammen ...")

    all_entries = []

    sources = [
        (TRAINING_DIR / "hime_training_filtered.jsonl", "JParaCrawl (gefiltert)"),
        (TRAINING_DIR / "shuukura_wn_aligned.jsonl",    "ShuuKura WN"),
    ]

    for filepath, name in sources:
        if not filepath.exists():
            print(f"[!] Nicht gefunden: {filepath.name}")
            continue

        count = 0
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                # Nur Paare mit echtem JP und EN Output
                if (entry.get("input") and len(entry["input"]) > 50 and
                    entry.get("output") and len(entry["output"]) > 50):
                    all_entries.append(entry)
                    count += 1

        print(f"[OK] {name}: {count:,} Paare")

    output_file = TRAINING_DIR / "hime_training_all.jsonl"
    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"\n{'='*60}")
    print(f"  Gesamt Trainingspaare: {len(all_entries):,}")
    print(f"  Davon ShuuKura WN:     {shuukura_count}")
    print(f"  Output: {output_file}")
    print(f"{'='*60}")
    print(f"\n  Hinweis: LN Volumes 3-7 wurden NICHT verwendet")
    print(f"  (Light Novel Version hat kein freies JP Pendant)")


if __name__ == "__main__":
    create_aligned_training_data()
