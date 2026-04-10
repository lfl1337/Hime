#!/usr/bin/env python3
"""Download all Pipeline v2 models from HuggingFace.

Usage:
    uv run scripts/download_models_v2.py
    uv run scripts/download_models_v2.py --model translategemma-12b
    uv run scripts/download_models_v2.py --list
    uv run scripts/download_models_v2.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)
MODELS_DIR = Path(os.environ.get("HIME_MODELS_DIR") or PROJECT_ROOT / "modelle")

MODELS: list[dict] = [
    {
        "key": "translategemma-12b",
        "hf_id": "google/translategemma-12b-it",
        "description": "Stage 1B — MT-spezialisierter Draft",
        "size_gb": 24,
        "method": "transformers",
        "local_dir": MODELS_DIR / "translategemma-12b",
    },
    {
        "key": "translategemma-27b",
        "hf_id": "google/translategemma-27b-it",
        "description": "Stage 2 — Merger",
        "size_gb": 54,
        "method": "transformers",
        "local_dir": MODELS_DIR / "translategemma-27b",
    },
    {
        "key": "qwen35-9b",
        "hf_id": "Qwen/Qwen3-9B",
        "description": "Stage 1C — Diversitäts-Draft",
        "size_gb": 18,
        "method": "unsloth",
        "local_dir": MODELS_DIR / "qwen35-9b",
    },
    {
        "key": "qwen35-35b",
        "hf_id": "Qwen/Qwen3-30B-A3B",
        "description": "Stage 3 — Polish",
        "size_gb": 20,
        "method": "unsloth",
        "local_dir": MODELS_DIR / "qwen35-35b",
    },
    {
        "key": "qwen35-2b",
        "hf_id": "Qwen/Qwen3-2B",
        "description": "Stage 4 — Reader Panel (15 Personas)",
        "size_gb": 1.2,
        "method": "unsloth",
        "local_dir": MODELS_DIR / "qwen35-2b",
    },
    {
        "key": "gemma4-e4b",
        "hf_id": "unsloth/gemma-4-E4B-it-GGUF",
        "description": "Stage 1D — Diversitäts-Draft (inference-only)",
        "size_gb": 3,
        "method": "gguf",
        "local_dir": MODELS_DIR / "gemma4-e4b",
        "include_pattern": "*.gguf",
    },
    {
        "key": "lfm2-24b",
        "hf_id": "LiquidAI/LFM2-24B-A2B",
        "description": "Stage 4 — Aggregator (Transformers >=5.0.0, kein Unsloth)",
        "size_gb": 14,
        "method": "transformers",
        "local_dir": MODELS_DIR / "lfm2-24b",
    },
    {
        "key": "lfm2-2b",
        "hf_id": "LiquidAI/LFM2-2.6B",
        "description": "Vault Organizer",
        "size_gb": 2.6,
        "method": "transformers",
        "local_dir": MODELS_DIR / "lfm2-2b",
    },
]


def _is_downloaded(model: dict) -> bool:
    local = model["local_dir"]
    if model["method"] == "gguf":
        return any(local.glob("*.gguf")) if local.exists() else False
    return (local / "config.json").exists()


def download_model(model: dict, dry_run: bool = False) -> None:
    from huggingface_hub import snapshot_download

    key = model["key"]
    hf_id = model["hf_id"]
    local_dir = model["local_dir"]

    if _is_downloaded(model):
        print(f"  [SKIP] {key} — bereits vorhanden in {local_dir}")
        return

    print(f"  [DOWN] {key} ({model['size_gb']}GB) — {hf_id}")
    if dry_run:
        print(f"         -> wuerde nach {local_dir} laden")
        return

    local_dir.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {
        "repo_id": hf_id,
        "local_dir": str(local_dir),
        "resume_download": True,
    }
    if "include_pattern" in model:
        kwargs["allow_patterns"] = [model["include_pattern"]]

    snapshot_download(**kwargs)
    print(f"  [OK]   {key} — fertig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Pipeline v2 models")
    parser.add_argument("--model", help="Nur ein spezifisches Modell laden (key)")
    parser.add_argument("--list", action="store_true", help="Verfuegbare Modelle auflisten")
    parser.add_argument("--dry-run", action="store_true", help="Nur zeigen was geladen wuerde")
    args = parser.parse_args()

    if args.list:
        print("\nVerfuegbare Modelle:")
        for m in MODELS:
            status = "[OK]" if _is_downloaded(m) else "[--]"
            print(f"  {status} {m['key']:20s} {m['size_gb']:5.1f}GB  {m['description']}")
        return

    targets = [m for m in MODELS if m["key"] == args.model] if args.model else MODELS
    if args.model and not targets:
        print(f"Unbekanntes Modell: {args.model}")
        print("Verfuegbare Keys:", [m["key"] for m in MODELS])
        sys.exit(1)

    total_gb = sum(m["size_gb"] for m in targets if not _is_downloaded(m))
    print(f"\nLade {len(targets)} Modell(e) — ~{total_gb:.1f}GB noch nicht vorhanden\n")
    for model in targets:
        download_model(model, dry_run=args.dry_run)
    print("\nFertig.")


if __name__ == "__main__":
    main()
