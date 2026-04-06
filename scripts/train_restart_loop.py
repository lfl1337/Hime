"""
Auto-Restart Training Loop for VRAM Fragmentation Workaround

Runs train_generic.py in cycles of --cycle-steps steps, saving each cycle's
checkpoints in a separate subdirectory:

    modelle/lora/<model>/
        cycle-1/checkpoint/checkpoint-20 .. checkpoint-150
        cycle-2/checkpoint/checkpoint-20 .. checkpoint-150
        ...
        adapter/   ← final merged adapter (last cycle only)

Each restart clears VRAM fragmentation via warm-start (fresh optimizer,
loaded adapter weights from previous cycle's latest checkpoint).

Usage:
    python train_restart_loop.py --model qwen32b --cycle-steps 150
    python train_restart_loop.py --model qwen32b --cycle-steps 150 --resume path/to/checkpoint
"""

import argparse
import json
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


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _cp_mtime(cp: Path) -> float:
    """Modification time of trainer_state.json — reliable on Windows."""
    ts = cp / "trainer_state.json"
    return ts.stat().st_mtime if ts.exists() else 0.0


def _cp_global_step(cp: Path) -> int:
    ts = cp / "trainer_state.json"
    if ts.exists():
        try:
            return json.loads(ts.read_text()).get("global_step", 0)
        except Exception:
            pass
    return int(cp.name.split("-")[1]) if re.fullmatch(r"checkpoint-\d+", cp.name) else 0


def latest_checkpoint(checkpoint_dir: Path) -> Path | None:
    """Return the most recently written checkpoint in checkpoint_dir."""
    if not checkpoint_dir.exists():
        return None
    checkpoints = [
        d for d in checkpoint_dir.iterdir()
        if d.is_dir() and re.fullmatch(r"checkpoint-\d+", d.name)
    ]
    if not checkpoints:
        return None
    return max(checkpoints, key=_cp_mtime)


def next_cycle_num(model_base: Path) -> int:
    """Return the next cycle number (1-based) by scanning existing cycle-N dirs."""
    existing = [
        d for d in model_base.iterdir()
        if d.is_dir() and re.fullmatch(r"cycle-\d+", d.name)
    ] if model_base.exists() else []
    if not existing:
        return 1
    return max(int(d.name.split("-")[1]) for d in existing) + 1


# ---------------------------------------------------------------------------
# Run one training cycle
# ---------------------------------------------------------------------------

def run_cycle(model: str, run_name: str, output_dir: Path,
              resume: str | None, cycle_steps: int,
              epochs: int, log_file: Path, extra_args: list) -> int:
    """Run one training cycle. Returns exit code."""
    cmd = [
        "conda", "run", "-n", "hime",
        "python", str(TRAIN_SCRIPT),
        "--model", model,
        "--run-name", run_name,
        "--epochs", str(epochs),
        "--log-file", str(log_file),
        "--output-dir", str(output_dir),
        "--max-steps", str(cycle_steps),
        *extra_args,
    ]
    if resume:
        cmd += ["--resume", resume]

    ts = datetime.now().strftime("%H:%M:%S")
    cycle_name = output_dir.name
    print(f"[{ts}] {cycle_name} | resume={Path(resume).name if resume else 'fresh'} | max_steps={cycle_steps}")
    sys.stdout.flush()
    result = subprocess.run(cmd)
    return result.returncode


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Auto-restart training loop with cycle directories")
    parser.add_argument("--model",       required=True, choices=list(MODEL_LORA_DIR.keys()))
    parser.add_argument("--run-name",    default=None)
    parser.add_argument("--epochs",      type=int, default=3)
    parser.add_argument("--resume",      default=None, help="Explicit initial checkpoint path")
    parser.add_argument("--cycle-steps", type=int, default=150,
                        help="Restart every N steps to clear VRAM fragmentation (default: 150)")
    parser.add_argument("--total-steps", type=int, default=None,
                        help="Stop loop after this many total steps across all cycles")
    parser.add_argument("--start-cycle", type=int, default=None,
                        help="Force starting cycle number (default: auto-detect)")
    args, extra = parser.parse_known_args()

    lora_dir  = MODEL_LORA_DIR[args.model]
    run_name  = args.run_name or lora_dir
    model_base = MODELS_DIR / run_name
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Determine starting cycle number
    cycle_num = args.start_cycle if args.start_cycle is not None else next_cycle_num(model_base)

    # Determine initial resume checkpoint
    resume = args.resume
    if resume is None:
        # Check previous cycle for latest checkpoint
        prev_cycle = model_base / f"cycle-{cycle_num - 1}" / "checkpoint"
        cp = latest_checkpoint(prev_cycle)
        if cp is not None:
            resume = str(cp)
            print(f"[auto] Resuming from {cp.parent.parent.name}/{cp.parent.name}/{cp.name}")
        else:
            # Fall back to flat checkpoint dir (legacy sessions)
            flat_cp_dir = model_base / "checkpoint"
            cp = latest_checkpoint(flat_cp_dir)
            if cp is not None:
                resume = str(cp)
                print(f"[auto] Resuming from legacy checkpoint: {cp.name}")

    if resume:
        print(f"[init] Starting at cycle-{cycle_num}, resume={Path(resume).name}")
    else:
        print(f"[init] Starting at cycle-{cycle_num}, fresh training")
    sys.stdout.flush()

    total_accumulated = 0

    while True:
        cycle_dir = model_base / f"cycle-{cycle_num}"
        ts_str    = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file  = LOG_DIR / f"{run_name}_{ts_str}.log"

        # Compute steps for this cycle
        if args.total_steps is not None:
            remaining = args.total_steps - total_accumulated
            if remaining <= 0:
                print(f"[done] Reached total_steps={args.total_steps}. Stopping.")
                break
            cycle_steps = min(args.cycle_steps, remaining)
        else:
            cycle_steps = args.cycle_steps

        rc = run_cycle(args.model, run_name, cycle_dir, resume,
                       cycle_steps, args.epochs, log_file, extra)

        if rc != 0:
            print(f"[!] cycle-{cycle_num} exited with code {rc}. Stopping loop.")
            sys.exit(rc)

        # Find latest checkpoint from this cycle
        cp = latest_checkpoint(cycle_dir / "checkpoint")
        if cp is None:
            print(f"[!] No checkpoint found in cycle-{cycle_num}. Stopping.")
            sys.exit(1)

        step = _cp_global_step(cp)
        total_accumulated += step
        print(f"[cycle-{cycle_num} done] Latest: {cycle_dir.name}/checkpoint/{cp.name} (step {step}, total ~{total_accumulated})")
        sys.stdout.flush()

        resume    = str(cp)
        cycle_num += 1

        # Brief pause between cycles
        time.sleep(5)


if __name__ == "__main__":
    main()
