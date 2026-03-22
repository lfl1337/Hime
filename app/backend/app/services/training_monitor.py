"""
Training monitor service.

Reads HuggingFace Trainer artifacts from disk (trainer_state.json files,
checkpoint directories, log files) and exposes them as typed Pydantic models.
No training logic lives here — this is purely a read-only observer.
"""
import asyncio
import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..config import settings


# ---------------------------------------------------------------------------
# Display name lookup table
# ---------------------------------------------------------------------------

_DISPLAY_NAMES: dict[str, str] = {
    "Qwen2.5-32B-Instruct": "Qwen 2.5 32B",
    "Qwen2.5-14B-Instruct": "Qwen 2.5 14B",
    "Qwen2.5-72B-Instruct": "Qwen 2.5 72B",
    "gemma-3-27b-it-GGUF": "Gemma 3 27B",
    "DeepSeek-R1-Distill-Qwen-32B-GGUF": "DeepSeek R1 32B",
    "Qwen2.5-32B-Instruct-GGUF": "Qwen 2.5 32B",
    "Qwen2.5-72B-Instruct-GGUF": "Qwen 2.5 72B",
    "Qwen2.5-14B-Instruct-GGUF": "Qwen 2.5 14B",
}


def _prettify_name(name: str) -> str:
    if name in _DISPLAY_NAMES:
        return _DISPLAY_NAMES[name]
    return (
        name
        .replace("-GGUF", "")
        .replace("-Instruct", "")
        .replace("-bnb-4bit", "")
        .removesuffix("-it")
        .replace("-", " ")
        .replace("_", " ")
        .strip()
        .title()
    )


# ---------------------------------------------------------------------------
# Pipeline role mapping
# ---------------------------------------------------------------------------

_PIPELINE_ROLES: dict[str, str] = {
    "gemma-3-27b-it-GGUF": "Stage 1 — Draft",
    "DeepSeek-R1-Distill-Qwen-32B-GGUF": "Stage 1 — Draft",
    "Qwen2.5-32B-Instruct-GGUF": "Stage 1 — Draft",
    "Qwen2.5-72B-Instruct-GGUF": "Stage 2 — Refine",
    "Qwen2.5-14B-Instruct-GGUF": "Stage 3 — Polish",
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class EtaInfo(BaseModel):
    pct: int
    current_step: int
    total_steps: int
    elapsed: str
    eta: str
    sec_per_it: float


class TrainingStatus(BaseModel):
    run_name: str
    model_name: str
    status: Literal["idle", "training", "interrupted", "complete"]
    current_step: int
    max_steps: int
    current_epoch: float
    max_epochs: float
    progress_pct: float
    best_checkpoint: str | None
    best_eval_loss: float | None
    latest_train_loss: float | None
    has_log_file: bool
    log_file_path: str | None
    scripts_path: str
    eta_info: EtaInfo | None = None


class CheckpointInfo(BaseModel):
    name: str
    step: int
    epoch: float
    eval_loss: float | None
    folder_size_mb: float
    timestamp: datetime
    is_best: bool
    is_last: bool
    is_interrupted: bool
    full_path: str


class LossPoint(BaseModel):
    step: int
    epoch: float
    train_loss: float | None
    eval_loss: float | None
    learning_rate: float | None


class RunInfo(BaseModel):
    run_name: str
    display_name: str
    status: Literal["idle", "training", "interrupted", "complete"]
    current_step: int
    max_steps: int
    progress_pct: float
    best_eval_loss: float | None
    has_active_log: bool


class GGUFModelInfo(BaseModel):
    name: str
    display_name: str
    size_gb: float
    file_count: int
    is_pipeline_model: bool
    pipeline_role: str | None  # "Stage 1 — Draft", "Stage 2 — Refine", "Stage 3 — Polish"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lora_base_dir() -> Path:
    return Path(settings.lora_path).parent


def _gguf_base_dir() -> Path:
    return Path(settings.models_base_path) / "lmstudio-community"


def _checkpoint_dir(run_name: str) -> Path:
    return _lora_base_dir() / run_name / "checkpoint"


def _find_log_for_run(run_name: str) -> Path | None:
    log_file = Path(settings.training_log_path) / f"{run_name}.log"
    return log_file if log_file.is_file() else None


def _read_trainer_state(path: Path) -> dict | None:
    state_file = path / "trainer_state.json"
    if not state_file.is_file():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _latest_trainer_state(run_name: str) -> dict | None:
    """Return the trainer_state.json from the checkpoint with the highest global_step."""
    cp_dir = _checkpoint_dir(run_name)
    if not cp_dir.is_dir():
        return None

    best_step = -1
    best_state: dict | None = None

    for child in cp_dir.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith("checkpoint-"):
            continue
        state = _read_trainer_state(child)
        if state is None:
            continue
        step = state.get("global_step", 0)
        if step > best_step:
            best_step = step
            best_state = state

    return best_state


def _derive_status(
    state: dict | None,
    run_name: str,
) -> Literal["idle", "training", "interrupted", "complete"]:
    cp_dir = _checkpoint_dir(run_name)
    # 1. Interrupted directory created by trainer.save_model() in KeyboardInterrupt handler
    if cp_dir.is_dir() and (cp_dir / "interrupted").is_dir():
        return "interrupted"

    if state is None:
        return "idle"

    # 2. Log file was modified recently
    log_file = _find_log_for_run(run_name)
    if log_file is not None:
        age = time.time() - log_file.stat().st_mtime
        if age < 120:
            return "training"

    # 3. Training completed
    max_steps = state.get("max_steps", 0)
    global_step = state.get("global_step", 0)
    if max_steps > 0 and global_step >= max_steps:
        return "complete"

    return "idle"


# ---------------------------------------------------------------------------
# ETA parsing
# ---------------------------------------------------------------------------

_TQDM_PATTERN = re.compile(
    r'(\d+)%\|.*?\|\s*(\d+)/(\d+)\s*\[(\S+)<(\S+),\s*([\d.]+)s/it\]'
)


def parse_eta_from_log(run: str) -> EtaInfo | None:
    log_file = Path(settings.training_log_path) / f"{run}.log"
    if not log_file.exists():
        return None
    try:
        with open(log_file, 'rb') as f:
            f.seek(max(0, os.path.getsize(log_file) - 5120))
            tail = f.read().decode('utf-8', errors='replace')
        for line in reversed(tail.splitlines()):
            m = _TQDM_PATTERN.search(line)
            if m:
                pct, cur, total, elapsed, eta, sec_per_it = m.groups()
                return EtaInfo(
                    pct=int(pct),
                    current_step=int(cur),
                    total_steps=int(total),
                    elapsed=elapsed,
                    eta=eta,
                    sec_per_it=float(sec_per_it),
                )
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_training_status(run_name: str) -> TrainingStatus:
    state = _latest_trainer_state(run_name)
    log_file = _find_log_for_run(run_name)
    status = _derive_status(state, run_name)
    model_name = run_name

    if state is None:
        return TrainingStatus(
            run_name=run_name,
            model_name=model_name,
            status="idle",
            current_step=0,
            max_steps=0,
            current_epoch=0.0,
            max_epochs=0.0,
            progress_pct=0.0,
            best_checkpoint=None,
            best_eval_loss=None,
            latest_train_loss=None,
            has_log_file=log_file is not None,
            log_file_path=str(log_file) if log_file else None,
            scripts_path=str(settings.scripts_path),
            eta_info=parse_eta_from_log(run_name),
        )

    global_step = state.get("global_step", 0)
    max_steps = state.get("max_steps", 0)
    epoch = state.get("epoch", 0.0)

    # Derive max_epochs from log_history if not directly available
    max_epochs = 0.0
    log_history = state.get("log_history", [])
    if log_history:
        max_epochs = max((e.get("epoch", 0.0) for e in log_history), default=0.0)
        # Round up to nearest integer for display
        max_epochs = math.ceil(max_epochs) if max_epochs > 0 else 3.0

    best_model_checkpoint = state.get("best_model_checkpoint")
    best_checkpoint = Path(best_model_checkpoint).name if best_model_checkpoint else None

    best_eval_loss = state.get("best_metric")

    # Latest training loss from log_history
    latest_train_loss: float | None = None
    for entry in reversed(log_history):
        if "loss" in entry and "eval_loss" not in entry:
            latest_train_loss = entry["loss"]
            break

    progress_pct = (global_step / max_steps * 100.0) if max_steps > 0 else 0.0

    return TrainingStatus(
        run_name=run_name,
        model_name=model_name,
        status=status,
        current_step=global_step,
        max_steps=max_steps,
        current_epoch=round(epoch, 4),
        max_epochs=max_epochs,
        progress_pct=round(progress_pct, 2),
        best_checkpoint=best_checkpoint,
        best_eval_loss=best_eval_loss,
        latest_train_loss=latest_train_loss,
        has_log_file=log_file is not None,
        log_file_path=str(log_file) if log_file else None,
        scripts_path=str(settings.scripts_path),
        eta_info=parse_eta_from_log(run_name),
    )


def get_checkpoints(run_name: str) -> list[CheckpointInfo]:
    cp_dir = _checkpoint_dir(run_name)
    if not cp_dir.is_dir():
        return []

    # Get the latest state to know best_model_checkpoint
    latest_state = _latest_trainer_state(run_name)
    best_model_checkpoint = None
    if latest_state:
        bmc = latest_state.get("best_model_checkpoint")
        best_model_checkpoint = Path(bmc).name if bmc else None

    entries: list[CheckpointInfo] = []
    max_step = -1

    # Collect all checkpoint-NNN dirs first to determine is_last
    cp_dirs = [c for c in cp_dir.iterdir() if c.is_dir() and c.name.startswith("checkpoint-")]
    for c in cp_dirs:
        try:
            step = int(c.name.split("-")[1])
            if step > max_step:
                max_step = step
        except (IndexError, ValueError):
            pass

    for child in cp_dir.iterdir():
        if not child.is_dir():
            continue

        is_interrupted = child.name == "interrupted"

        if is_interrupted:
            # No trainer_state.json here; use data from latest state
            if latest_state:
                step = latest_state.get("global_step", 0)
                epoch = latest_state.get("epoch", 0.0)
            else:
                step, epoch = 0, 0.0
            try:
                folder_size_mb = sum(f.stat().st_size for f in child.rglob("*") if f.is_file()) / 1e6
                timestamp = datetime.fromtimestamp(child.stat().st_mtime)
            except Exception:
                folder_size_mb = 0.0
                timestamp = datetime.now()
            entries.append(CheckpointInfo(
                name="interrupted",
                step=step,
                epoch=round(epoch, 4),
                eval_loss=None,
                folder_size_mb=round(folder_size_mb, 2),
                timestamp=timestamp,
                is_best=False,
                is_last=False,
                is_interrupted=True,
                full_path=str(child),
            ))
            continue

        if not child.name.startswith("checkpoint-"):
            continue

        state = _read_trainer_state(child)
        if state is None:
            continue

        try:
            step = int(child.name.split("-")[1])
        except (IndexError, ValueError):
            continue

        epoch = state.get("epoch", 0.0)

        # Last eval entry gives eval_loss for this checkpoint
        eval_loss: float | None = None
        for entry in reversed(state.get("log_history", [])):
            if "eval_loss" in entry:
                eval_loss = entry["eval_loss"]
                break

        try:
            folder_size_mb = sum(f.stat().st_size for f in child.rglob("*") if f.is_file()) / 1e6
            timestamp = datetime.fromtimestamp(child.stat().st_mtime)
        except Exception:
            folder_size_mb = 0.0
            timestamp = datetime.now()

        is_best = best_model_checkpoint == child.name
        is_last = step == max_step

        entries.append(CheckpointInfo(
            name=child.name,
            step=step,
            epoch=round(epoch, 4),
            eval_loss=eval_loss,
            folder_size_mb=round(folder_size_mb, 2),
            timestamp=timestamp,
            is_best=is_best,
            is_last=is_last,
            is_interrupted=False,
            full_path=str(child),
        ))

    # Sort: regular checkpoints by step ascending, interrupted at the end
    entries.sort(key=lambda e: (e.is_interrupted, e.step))
    return entries


def get_loss_history(run_name: str) -> list[LossPoint]:
    """Read log_history from the latest checkpoint's trainer_state.json."""
    state = _latest_trainer_state(run_name)
    if state is None:
        return []

    log_history = state.get("log_history", [])

    # Merge entries by step into LossPoint objects
    points: dict[int, LossPoint] = {}
    for entry in log_history:
        step = entry.get("step", 0)
        epoch = entry.get("epoch", 0.0)

        if step not in points:
            points[step] = LossPoint(step=step, epoch=epoch, train_loss=None, eval_loss=None, learning_rate=None)

        if "eval_loss" in entry:
            # Eval entry
            points[step].eval_loss = entry["eval_loss"]
        elif "loss" in entry:
            # Training entry
            points[step].train_loss = entry["loss"]
            points[step].learning_rate = entry.get("learning_rate")

    return sorted(points.values(), key=lambda p: p.step)


def get_log_tail(run_name: str, n: int = 20) -> list[str]:
    """Return the last n lines of the training log file for the given run."""
    log_file = _find_log_for_run(run_name)
    if log_file is None or not log_file.is_file():
        return []
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:] if len(lines) > n else lines
    except Exception:
        return []


def get_all_runs() -> list[RunInfo]:
    """Scan the LoRA base directory and return a RunInfo for each run that has a checkpoint/ folder."""
    try:
        lora_base = _lora_base_dir()
        if not lora_base.is_dir():
            return []
    except Exception:
        return []

    results: list[RunInfo] = []

    for entry in lora_base.iterdir():
        if not entry.is_dir():
            continue
        run_name = entry.name
        cp_dir = entry / "checkpoint"
        if not cp_dir.is_dir():
            continue

        state = _latest_trainer_state(run_name)
        status = _derive_status(state, run_name)

        global_step = state.get("global_step", 0) if state else 0
        max_steps = state.get("max_steps", 0) if state else 0
        best_eval_loss: float | None = state.get("best_metric") if state else None
        progress_pct = round((global_step / max_steps * 100.0) if max_steps > 0 else 0.0, 2)

        # Check if log file was modified within the last 300 seconds
        log_file = _find_log_for_run(run_name)
        has_active_log = False
        if log_file is not None:
            try:
                age = time.time() - log_file.stat().st_mtime
                has_active_log = age < 300
            except Exception:
                has_active_log = False

        results.append(RunInfo(
            run_name=run_name,
            display_name=_prettify_name(run_name),
            status=status,
            current_step=global_step,
            max_steps=max_steps,
            progress_pct=progress_pct,
            best_eval_loss=best_eval_loss,
            has_active_log=has_active_log,
        ))

    results.sort(key=lambda r: r.run_name)
    return results


def get_gguf_models() -> list[GGUFModelInfo]:
    """Scan the GGUF models directory and return info about each model folder."""
    try:
        gguf_base = _gguf_base_dir()
        if not gguf_base.is_dir():
            return []
    except Exception:
        return []

    results: list[GGUFModelInfo] = []

    for entry in gguf_base.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name

        # Count .gguf files and compute total size
        gguf_files = list(entry.glob("*.gguf"))
        file_count = len(gguf_files)
        total_bytes = 0
        for f in gguf_files:
            try:
                total_bytes += f.stat().st_size
            except Exception:
                pass
        size_gb = round(total_bytes / 1e9, 2)

        pipeline_role = _PIPELINE_ROLES.get(name)
        is_pipeline_model = pipeline_role is not None

        results.append(GGUFModelInfo(
            name=name,
            display_name=_prettify_name(name),
            size_gb=size_gb,
            file_count=file_count,
            is_pipeline_model=is_pipeline_model,
            pipeline_role=pipeline_role,
        ))

    # Sort: pipeline models first, then by name
    results.sort(key=lambda m: (not m.is_pipeline_model, m.name))
    return results


# ---------------------------------------------------------------------------
# Log line classification
# ---------------------------------------------------------------------------

def _classify_log_line(line: str) -> str:
    """Return a type tag for a training log line."""
    if "[CHECKPOINT]" in line:
        return "checkpoint"
    if "[HW]" in line:
        return "hardware"
    if any(tag in line for tag in ("[INFO]", "[FERTIG]", "[UNTERBROCHEN]", "[OK]", "[i]", "[..]")):
        return "info"
    if re.search(r"'loss'\s*:", line):
        return "loss"
    if re.search(r"\d+%\|", line):
        return "progress"
    if re.search(r"\b(ERROR|CRITICAL)\b", line):
        return "error"
    return "info"


# ---------------------------------------------------------------------------
# Hardware log helper
# ---------------------------------------------------------------------------

def _write_hw_snapshot_to_log(run_name: str) -> None:
    """Append a [HW] hardware snapshot line to the training log file."""
    log_file = _find_log_for_run(run_name)
    if log_file is None:
        return
    try:
        from .hardware_monitor import get_hardware_stats
        stats = get_hardware_stats()
        ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        vram_used = stats.gpu_vram_used_mb / 1024
        vram_total = stats.gpu_vram_total_mb / 1024
        line1 = (
            f"{ts} [HW] GPU: {vram_used:.1f}/{vram_total:.1f} GB VRAM"
            f" | {stats.gpu_utilization_pct}% util"
            f" | {stats.gpu_temp_celsius}°C"
            f" | {stats.gpu_power_draw_w:.0f}W\n"
        )
        line2 = (
            f"{ts} [HW] RAM: {stats.ram_used_gb:.1f}/{stats.ram_total_gb:.1f} GB"
            f" | CPU: {stats.cpu_utilization_pct:.0f}%\n"
        )
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line1)
            f.write(line2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

async def stream_events(run_name: str):
    """Async generator — emits 'status' events every 30 seconds, only when changed.
    Log lines and loss points are no longer streamed; fetch them on demand via REST."""
    last_status_json: str | None = None

    while True:
        try:
            status = get_training_status(run_name)
            status_json = status.model_dump_json()
            if status_json != last_status_json:
                yield {"event": "status", "data": status_json}
                last_status_json = status_json
        except Exception:
            pass  # Never crash the SSE stream
        await asyncio.sleep(30)
