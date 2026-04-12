"""Offline structure check for bge-m3 (Phase 2 Task 2.6)."""
import pathlib

d = pathlib.Path("N:/Projekte/NiN/Hime/modelle/embeddings/bge-m3")
required = [
    "config.json",
    "tokenizer.json",
    "sentencepiece.bpe.model",
    "config_sentence_transformers.json",
    "pytorch_model.bin",
]
all_ok = True
for f in required:
    p = d / f
    status = "OK" if p.exists() else "FAIL"
    if not p.exists():
        all_ok = False
    size = f"{p.stat().st_size / 1024**2:.1f} MB" if p.exists() else "missing"
    print(f"[{status}] {f} ({size})")

if all_ok:
    print("[OK] bge-m3 directory structure (all required files present)")
else:
    print("[FAIL] bge-m3 missing required files")
