"""Validate line 131 references the correct file. No training, no model load."""
from pathlib import Path

src = Path("N:/Projekte/NiN/Hime/scripts/train_hime.py").read_text(encoding="utf-8")
lines = src.splitlines()
line_131 = lines[130]  # 0-indexed

print(f"Line 131: {line_131!r}")

assert "hime_training_all.jsonl" in line_131, (
    f"FAIL: Line 131 still has wrong file: {line_131!r}"
)
assert "jparacrawl_500k.jsonl" not in line_131, (
    f"FAIL: jparacrawl_500k.jsonl found in line 131: {line_131!r}"
)
print("PASS: Line 131 correctly references hime_training_all.jsonl")
