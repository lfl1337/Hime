"""
Hime - Kakuyomu Scraper v3
Navigiert sequenziell durch alle Episoden via "nächste Episode" Links.
"""

import json, time, re, zipfile
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm import tqdm

PROJECT_ROOT = Path(r"C:\Projekte\Hime")
RAW_JP_DIR   = PROJECT_ROOT / "data" / "raw_jp"
RAW_EN_DIR   = PROJECT_ROOT / "data" / "raw_en"
TRAINING_DIR = PROJECT_ROOT / "data" / "training"
EPUB_DIR     = PROJECT_ROOT / "data" / "epubs"

for d in [RAW_JP_DIR, RAW_EN_DIR, TRAINING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}
DELAY    = 2.0
WORK_ID  = "1177354054894027232"
FIRST_EP = "1177354054894027298"
BASE     = "https://kakuyomu.jp"
SKIP_PAGES = ['cover','title','toc','nav','copyright','contents','afterword']

INSTRUCTION = (
    "Translate the following Japanese yuri light novel text to English. "
    "This is from 'Shuu ni Ichido Kurasumeito wo Kau Hanashi'. "
    "Preserve the intimate slow-burn tone and the nuanced relationship between Miyagi and Sendai."
)


def scrape_episode_and_get_next(url: str) -> tuple:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except:
        return "", None, ""

    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1: title = h1.get_text(strip=True)

    text = ""
    next_url = None

    # __NEXT_DATA__ auslesen
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd:
        try:
            data = json.loads(nd.string)

            def find_text(obj, depth=0):
                if depth > 10: return ""
                if isinstance(obj, dict):
                    for k in ["body","text","content","bodyText","episodeBody"]:
                        if k in obj and isinstance(obj[k], str) and len(obj[k]) > 200:
                            return obj[k]
                    for v in obj.values():
                        r = find_text(v, depth+1)
                        if r: return r
                elif isinstance(obj, list):
                    for i in obj:
                        r = find_text(i, depth+1)
                        if r: return r
                return ""

            def find_next(obj, depth=0):
                if depth > 10: return None
                if isinstance(obj, dict):
                    for k in ["nextEpisode","next","nextEpisodeId"]:
                        if k in obj:
                            v = obj[k]
                            if isinstance(v, dict):
                                eid = v.get("id") or v.get("__id")
                                if eid: return str(eid)
                            elif isinstance(v, str) and v.isdigit() and len(v) > 10:
                                return v
                    for v in obj.values():
                        r = find_next(v, depth+1)
                        if r: return r
                elif isinstance(obj, list):
                    for i in obj:
                        r = find_next(i, depth+1)
                        if r: return r
                return None

            raw = find_text(data)
            if raw:
                raw = re.sub(r'<br\s*/?>', '\n', raw)
                raw = re.sub(r'<[^>]+>', '', raw)
                text = raw.strip()

            nid = find_next(data)
            if nid:
                next_url = f"{BASE}/works/{WORK_ID}/episodes/{nid}"

        except:
            pass

    # HTML Fallback Text
    if not text:
        for tag, attrs in [
            ("div", {"class": "widget-episodeBody"}),
            ("div", {"class": "js-episode-body"}),
        ]:
            c = soup.find(tag, attrs)
            if c:
                paras = [p.get_text().strip() for p in c.find_all("p") if p.get_text().strip()]
                if paras:
                    text = "\n".join(paras)
                    break

    # HTML Fallback Next Link
    if not next_url:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            lt = a.get_text(strip=True)
            if f"/works/{WORK_ID}/episodes/" in href and any(kw in lt for kw in ["次","next","→",">>"]):
                next_url = f"{BASE}{href}" if href.startswith("/") else href
                break

    return text, next_url, title


def scrape_shuukura_jp(max_episodes: int = 409):
    print(f"\n{'='*60}")
    print(f"  Kakuyomu JP Scraper v3")
    print(f"  409 Episoden via sequenzielle Navigation")
    print(f"{'='*60}\n")

    save_dir = RAW_JP_DIR / "ShuuKura"
    save_dir.mkdir(exist_ok=True)

    current_url = f"{BASE}/works/{WORK_ID}/episodes/{FIRST_EP}"
    saved = failed = 0
    ep_num = 1
    pbar = tqdm(total=max_episodes, desc="JP ShuuKura")

    while current_url and ep_num <= max_episodes:
        save_path = save_dir / f"ep_{str(ep_num).zfill(4)}.txt"

        if save_path.exists():
            _, next_url, _ = scrape_episode_and_get_next(current_url)
            current_url = next_url
            ep_num += 1
            pbar.update(1)
            time.sleep(0.5)
            continue

        text, next_url, title = scrape_episode_and_get_next(current_url)

        if text:
            save_path.write_text(f"# {title}\n\n{text}", encoding="utf-8")
            saved += 1
        else:
            failed += 1

        pbar.update(1)
        current_url = next_url
        ep_num += 1

        if not next_url:
            print(f"\n[i] Kein nächster Link bei Ep {ep_num-1}, stoppe.")
            break

        time.sleep(DELAY)

    pbar.close()
    print(f"\n[OK] {saved} gespeichert, {failed} fehlgeschlagen → {save_dir}")
    return saved


def extract_all_en_epubs():
    print(f"\n[..] Extrahiere ShuuKura EN EPUBs ...")
    save_dir = RAW_EN_DIR / "ShuuKura"
    save_dir.mkdir(exist_ok=True)

    epub_files = [f for f in sorted(EPUB_DIR.glob("*.epub")) if not re.match(r'^\d{2}_?\.epub$', f.name)]
    seen_sizes, unique_epubs = set(), []
    for f in epub_files:
        s = f.stat().st_size
        if s not in seen_sizes:
            seen_sizes.add(s)
            unique_epubs.append(f)

    print(f"[OK] {len(unique_epubs)} ShuuKura EN EPUBs")
    count = 0

    for epub_path in unique_epubs:
        sections = []
        with zipfile.ZipFile(epub_path, 'r') as z:
            for xf in sorted([f for f in z.namelist() if f.endswith(('.xhtml','.html')) and not any(s in f.lower() for s in SKIP_PAGES)]):
                content = z.read(xf).decode('utf-8', errors='ignore')
                soup = BeautifulSoup(content, 'html.parser')
                body = soup.find('body')
                if not body: continue
                paras = [p.get_text().strip() for p in body.find_all('p') if len(p.get_text().strip()) > 20]
                text = '\n\n'.join(paras)
                if len(text) > 200: sections.append(text)

        if sections:
            print(f"     {epub_path.name}: {len(sections)} Sektionen")
            for i, text in enumerate(sections):
                sp = save_dir / f"{epub_path.stem}_sec_{str(i).zfill(4)}.txt"
                if not sp.exists():
                    sp.write_text(text, encoding="utf-8")
                    count += 1

    print(f"[OK] {count} neue EN Sektionen → {save_dir}")
    return count


def create_training_data() -> int:
    jp_dir = RAW_JP_DIR / "ShuuKura"
    if not jp_dir.exists(): return 0
    output_file = TRAINING_DIR / "shuukura_jp.jsonl"
    count = 0
    with open(output_file, "w", encoding="utf-8") as f:
        for jp_file in tqdm(sorted(jp_dir.glob("*.txt")), desc="Training"):
            text = jp_file.read_text(encoding="utf-8").strip()
            if len(text) < 100: continue
            lines = text.split('\n')
            title = lines[0].lstrip("# ").strip() if lines[0].startswith("#") else ""
            body = '\n'.join(lines[2:]).strip() if title else text
            for chunk in [body[i:i+2500] for i in range(0, len(body), 2500)]:
                if len(chunk) < 100: continue
                f.write(json.dumps({"instruction": INSTRUCTION, "input": chunk, "output": "",
                    "source": "ShuuKura", "episode": jp_file.stem, "title": title,
                    "status": "needs_translation"}, ensure_ascii=False) + "\n")
                count += 1
    print(f"[OK] {count} Chunks → {output_file}")
    return count


def main():
    print("=" * 60)
    print("  Hime - ShuuKura Scraper v3")
    print("=" * 60)
    jp = scrape_shuukura_jp(max_episodes=409)
    en = extract_all_en_epubs()
    tr = create_training_data()
    print(f"\n{'='*60}")
    print(f"  JP Episoden:     {jp}")
    print(f"  EN Sektionen:    {en}")
    print(f"  Training Chunks: {tr}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
