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
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_aborted_by_signal = False


def _signal_handler(signum, frame):
    global _aborted_by_signal
    _aborted_by_signal = True


# Install handlers at import time so subprocess Ctrl+C also reaches us
signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)

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


def _setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hime.train_with_resume")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def _log_event(log_path: Path, event: str, **fields) -> None:
    entry = {"ts": datetime.now(UTC).isoformat(), "event": event, **fields}
    logger = _setup_logger(log_path)
    logger.info(json.dumps(entry, ensure_ascii=False))


def run_training_subprocess(cmd: list[str], log_path: Path) -> int:
    """Run the underlying training script and return its exit code."""
    _log_event(log_path, "subprocess_start", cmd=cmd)
    proc = subprocess.run(cmd)  # noqa: S603
    _log_event(log_path, "subprocess_exit", returncode=proc.returncode)
    return proc.returncode


def _read_curriculum_promotion_flag(state_path: Path | None) -> bool:
    if state_path is None or not state_path.exists():
        return False
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return bool(data.get("should_promote_tier"))
    except Exception:
        return False


def _clear_curriculum_promotion_flag(state_path: Path) -> None:
    """Increment tier index and clear the flag."""
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["current_tier_index"] = int(data["current_tier_index"]) + 1
    data["should_promote_tier"] = False
    data["last_updated"] = datetime.now(UTC).isoformat()
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(state_path)


def _rebuild_cmd_with_resume(base_cmd: list[str], newest_checkpoint: Path | None) -> list[str]:
    """Strip any existing --resume_from_checkpoint and re-append the newest one."""
    new_cmd: list[str] = []
    skip_next = False
    for tok in base_cmd:
        if skip_next:
            skip_next = False
            continue
        if tok == "--resume_from_checkpoint":
            skip_next = True
            continue
        new_cmd.append(tok)
    if newest_checkpoint is not None:
        new_cmd += ["--resume_from_checkpoint", str(newest_checkpoint)]
    return new_cmd


def run_with_retries(
    *,
    cmd: list[str],
    log_path: Path,
    max_restarts: int,
    checkpoint_dir: Path,
    model_name: str,
    model_key: str | None,
    epochs: float,
    curriculum_state_path: Path | None,
) -> int:
    """Run the training subprocess with crash retry. Returns the final exit code."""
    consecutive_failures = 0
    while True:
        rc = run_training_subprocess(cmd, log_path)

        if _aborted_by_signal:
            _log_event(log_path, "aborted_by_signal", model=model_name, returncode=rc)
            return rc

        if rc == 0:
            if _read_curriculum_promotion_flag(curriculum_state_path):
                if curriculum_state_path is not None:
                    _clear_curriculum_promotion_flag(curriculum_state_path)
                _log_event(log_path, "tier_promotion_handled", model=model_name)
            return 0

        consecutive_failures += 1
        _log_event(
            log_path, "subprocess_crash",
            attempt=consecutive_failures, max_attempts=max_restarts, returncode=rc,
        )
        if consecutive_failures > max_restarts:
            _log_event(log_path, "max_restarts_exceeded", model=model_name)
            return rc

        time.sleep(30)

        newest = find_newest_valid_checkpoint(checkpoint_dir)
        cmd = _rebuild_cmd_with_resume(base_cmd=cmd, newest_checkpoint=newest)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    models_dir = Path(os.environ.get("HIME_MODELS_DIR", str(PROJECT_ROOT / "modelle")))
    checkpoint_dir = models_dir / "lora" / args.model_name / "checkpoint"
    log_path = PROJECT_ROOT / "app" / "backend" / "logs" / "training" / "auto_resume.log"
    curriculum_state_path = models_dir / "lora" / args.model_name / "curriculum_state.json"

    newest = find_newest_valid_checkpoint(checkpoint_dir)

    if args.model_key:
        script = PROJECT_ROOT / "scripts" / "train_generic.py"
        cmd = [
            sys.executable, str(script),
            "--model", args.model_key,
            "--run-name", args.model_name,
            "--epochs", str(args.epochs),
        ]
    else:
        script = PROJECT_ROOT / "scripts" / "train_hime.py"
        cmd = [
            sys.executable, str(script),
            "--num_train_epochs", str(args.epochs),
        ]

    if newest is not None:
        cmd += ["--resume_from_checkpoint", str(newest)]
        print(f"[wrapper] Resuming from: {newest}")
        _log_event(log_path, "resume_decided", checkpoint=str(newest), model=args.model_name)
    else:
        print(f"[wrapper] No valid checkpoint found in {checkpoint_dir}")
        if not args.no_prompt:
            print("[wrapper] Start training from scratch? [Y/n] (10s timeout, default N)")
            try:
                import select
                if sys.platform == "win32":
                    answer = input().strip().lower()
                else:
                    rlist, _, _ = select.select([sys.stdin], [], [], 10)
                    answer = sys.stdin.readline().strip().lower() if rlist else "n"
            except Exception:
                answer = "n"
            if answer not in {"y", "yes"}:
                print("[wrapper] Aborting — no checkpoint and user did not confirm fresh start")
                return 1
        _log_event(log_path, "fresh_start", model=args.model_name)

    if args.dry_run:
        print("[wrapper] --dry-run set; exiting before launching training")
        print("[wrapper] cmd:", " ".join(cmd))
        return 0

    return run_with_retries(
        cmd=cmd,
        log_path=log_path,
        max_restarts=args.max_restarts,
        checkpoint_dir=checkpoint_dir,
        model_name=args.model_name,
        model_key=args.model_key,
        epochs=args.epochs,
        curriculum_state_path=curriculum_state_path,
    )


if __name__ == "__main__":
    sys.exit(main())
