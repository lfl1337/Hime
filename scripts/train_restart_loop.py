"""
Auto-Restart Training Loop for VRAM Fragmentation Workaround

Runs train_generic.py in cycles of --cycle-steps steps, then restarts
from the latest checkpoint. Each restart clears VRAM fragmentation via
warm-start (fresh optimizer, loaded adapter weights).

Usage:
    python train_restart_loop.py --model qwen32b --cycle-steps 200
    python train_restart_loop.py --model qwen32b --cycle-steps 200 --resume path/to/checkpoint
"""

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Projekte\Hime")
MODELS_DIR   = PROJECT_ROOT / "modelle" / "lora"
LOG_DIR      = PROJECT_ROOT / "app" / "backend" / "logs" / "training"

MODEL_LORA_DIR = {
    'qwen32b':  'Qwen2.5-32B-Instruct',
    'qwen14b':  'Qwen2.5-14B-Instruct',
    'qwen72b':  'Qwen2.5-72B-Instruct',
    'gemma27b': 'Gemma-3-27B-IT',
    'deepseek': 'DeepSeek-R1-Distill-Qwen-32B',
}

TRAIN_SCRIPT = PROJECT_ROOT / "scripts" / "train_generic.py"


def latest_checkpoint(checkpoint_dir: Path) -> Path | None:
    """Return the checkpoint with the highest step number."""
    checkpoints = [
        d for d in checkpoint_dir.iterdir()
        if d.is_dir() and re.fullmatch(r"checkpoint-\d+", d.name)
    ]
    if not checkpoints:
        return None
    return max(checkpoints, key=lambda d: int(d.name.split("-")[1]))


def checkpoint_step(cp: Path) -> int:
    return int(cp.name.split("-")[1])


def run_cycle(model: str, run_name: str, resume: str | None, cycle_steps: int,
              epochs: int, log_file: Path, extra_args: list) -> int:
    """Run one training cycle. Returns exit code."""
    cmd = [
        "conda", "run", "-n", "hime",
        "python", str(TRAIN_SCRIPT),
        "--model", model,
        "--run-name", run_name,
        "--epochs", str(epochs),
        "--log-file", str(log_file),
        "--max-steps", str(cycle_steps),
        *extra_args,
    ]
    if resume:
        cmd += ["--resume", resume]

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Starting cycle | resume={Path(resume).name if resume else 'fresh'} | max_steps={cycle_steps}")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Auto-restart training loop")
    parser.add_argument("--model",       required=True, choices=list(MODEL_LORA_DIR.keys()))
    parser.add_argument("--run-name",    default=None)
    parser.add_argument("--epochs",      type=int, default=3)
    parser.add_argument("--resume",      default=None, help="Initial checkpoint to resume from")
    parser.add_argument("--cycle-steps", type=int, default=200,
                        help="Restart every N steps to clear VRAM fragmentation (default: 200)")
    parser.add_argument("--total-steps", type=int, default=None,
                        help="Stop loop after this many total steps across all cycles")
    args, extra = parser.parse_known_args()

    lora_dir  = MODEL_LORA_DIR[args.model]
    run_name  = args.run_name or lora_dir
    cp_dir    = MODELS_DIR / run_name / "checkpoint"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    resume    = args.resume
    cycle_num = 0
    steps_done = 0

    # If no explicit resume given, find latest existing checkpoint
    if resume is None and cp_dir.exists():
        cp = latest_checkpoint(cp_dir)
        if cp:
            resume = str(cp)
            steps_done = checkpoint_step(cp)
            print(f"[auto] Found latest checkpoint: {cp.name} (step {steps_done})")

    while True:
        cycle_num += 1
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = LOG_DIR / f"{run_name}_{ts_str}.log"

        # Compute how many steps to run this cycle
        if args.total_steps is not None:
            remaining = args.total_steps - steps_done
            if remaining <= 0:
                print(f"[done] Reached total_steps={args.total_steps}. Stopping.")
                break
            cycle_steps = min(args.cycle_steps, remaining)
        else:
            cycle_steps = args.cycle_steps

        rc = run_cycle(args.model, run_name, resume, cycle_steps,
                       args.epochs, log_file, extra)

        if rc != 0:
            print(f"[!] Cycle {cycle_num} exited with code {rc}. Stopping loop.")
            sys.exit(rc)

        # Find new latest checkpoint
        cp = latest_checkpoint(cp_dir)
        if cp is None:
            print(f"[!] No checkpoint found after cycle {cycle_num}. Stopping.")
            sys.exit(1)

        new_step = checkpoint_step(cp)
        print(f"[cycle {cycle_num} done] Latest checkpoint: {cp.name} (step {new_step})")

        if new_step <= steps_done:
            print(f"[!] No progress made (step stayed at {steps_done}). Stopping.")
            sys.exit(1)

        steps_done = new_step
        resume = str(cp)

        # Brief pause between cycles to let GPU settle
        time.sleep(5)


if __name__ == "__main__":
    main()
