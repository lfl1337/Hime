import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)
DATA_FILE = PROJECT_ROOT / "data" / "raw_jparacrawl" / "extracted" / "en-ja" / "en-ja.bicleaner05.txt"

with open(DATA_FILE, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        print(f"Zeile {i+1}: {repr(line)}")
        if i >= 4:
            break
