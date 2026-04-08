"""
Crash-resilient training wrapper.

Discovers the newest valid checkpoint, invokes the underlying training script
with `--resume_from_checkpoint`, and retries on crash. Ensures we never lose
training progress to a missing-resume bug like the v1.2.0 disaster.

Usage:
    python scripts/train_with_resume.py \\
        --model-name Qwen2.5-32B-Instruct \\
        --epochs 1.5

Or with model_key (uses train_generic.py):
    python scripts/train_with_resume.py \\
        --model-name Qwen2.5-32B-Instruct \\
        --model-key qwen32b \\
        --epochs 1.5

CRITICAL: Do not run this against the currently active training output dir
while another training process is using it. The wrapper will refuse to start
if it detects a stale-or-active PID file.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Resolve project root from this file's location (no hardcoded paths)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT", str(SCRIPT_DIR.parent)))


_CHECKPOINT_NAME = re.compile(r"^checkpoint-(\d+)$")


def find_newest_valid_checkpoint(checkpoint_dir: Path) -> Path | None:
    """
    Return the path to the newest checkpoint folder that contains all of:
      - trainer_state.json
      - optimizer.pt
      - scheduler.pt

    A "newest" checkpoint is decided by the integer step number suffix
    (`checkpoint-<N>`), not by mtime — checkpoint-1000 is newer than
    checkpoint-200 even if it was touched earlier.

    Returns None if no valid checkpoint exists.
    """
    if not checkpoint_dir.exists():
        return None

    candidates: list[tuple[int, Path]] = []
    for entry in checkpoint_dir.iterdir():
        if not entry.is_dir():
            continue
        m = _CHECKPOINT_NAME.match(entry.name)
        if not m:
            continue
        if not (entry / "trainer_state.json").exists():
            continue
        if not (entry / "optimizer.pt").exists():
            continue
        if not (entry / "scheduler.pt").exists():
            continue
        candidates.append((int(m.group(1)), entry))

    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crash-resilient training wrapper")
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-key", default=None,
                        choices=["qwen32b", "qwen14b", "qwen72b", "gemma27b", "deepseek"])
    parser.add_argument("--epochs", type=float, default=1.5)
    parser.add_argument("--no-prompt", action="store_true",
                        help="Skip the 10s confirmation when no checkpoint is found")
    parser.add_argument("--max-restarts", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the resolved command and exit without running")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Resolve checkpoint dir without importing app.core.paths (this script may
    # run in a conda env that doesn't have the backend installed)
    models_dir = Path(os.environ.get("HIME_MODELS_DIR", str(PROJECT_ROOT / "modelle")))
    checkpoint_dir = models_dir / "lora" / args.model_name / "checkpoint"

    newest = find_newest_valid_checkpoint(checkpoint_dir)
    if newest:
        print(f"[wrapper] Resuming from: {newest}")
    else:
        print(f"[wrapper] No valid checkpoint found in {checkpoint_dir}")

    if args.dry_run:
        print("[wrapper] --dry-run set; exiting before launching training")
        return 0

    # Crash retry loop is implemented in Task 5
    raise NotImplementedError("Retry loop is implemented in a follow-up task")


if __name__ == "__main__":
    sys.exit(main())
