"""Start/stop LoRA training jobs from the app UI."""
import json
import logging
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psutil
from pydantic import BaseModel

from ..config import settings

_log = logging.getLogger(__name__)

# Maps model_key → canonical LoRA output directory name (must match frontend MODEL_TO_LORA_DIR)
MODEL_KEY_TO_RUN_NAME: dict[str, str] = {
    'qwen32b':  'Qwen2.5-32B-Instruct',
    'qwen14b':  'Qwen2.5-14B-Instruct',
    'qwen72b':  'Qwen2.5-72B-Instruct',
    'gemma27b': 'Gemma-3-27B-IT',
    'deepseek': 'DeepSeek-R1-Distill-Qwen-32B',
}


class TrainingProcess(BaseModel):
    model_name: str
    pid: int
    started_at: datetime
    checkpoint: str | None
    log_file: str
    epochs: int


def _lora_dir(model_name: str) -> Path:
    return Path(settings.models_base_path) / "lora" / model_name


def _checkpoint_dir(model_name: str) -> Path:
    return _lora_dir(model_name) / "checkpoint"


def _pid_file(model_name: str) -> Path:
    return Path(settings.training_log_path) / f"{model_name}.pid.json"


def _log_file(model_name: str) -> str:
    return str(Path(settings.training_log_path) / f"{model_name}.log")


def _ensure_log_dir() -> None:
    Path(settings.training_log_path).mkdir(parents=True, exist_ok=True)


def _is_process_alive(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def start_training(
    model_name: str,
    resume_checkpoint: str | None = None,
    epochs: int = 3,
    model_key: str | None = None,
) -> TrainingProcess:
    conda_env = "hime"
    # If model_key is provided, enforce the canonical run name so PID/log/checkpoint
    # paths are consistent regardless of what model_name the caller passed.
    if model_key and model_key in MODEL_KEY_TO_RUN_NAME:
        canonical = MODEL_KEY_TO_RUN_NAME[model_key]
        if model_name != canonical:
            _log.info("Correcting model_name %r → %r for model_key %r", model_name, canonical, model_key)
            model_name = canonical

    _log.info("Starting training for %s (epochs=%d, model_key=%s)", model_name, epochs, model_key)
    _ensure_log_dir()
    pid_path = _pid_file(model_name)
    if pid_path.exists():
        data = json.loads(pid_path.read_text())
        if _is_process_alive(data["pid"]):
            raise RuntimeError(f"Training already running for {model_name} (PID {data['pid']})")
        # Stale PID file — clean it up and allow fresh start
        _log.warning("Stale PID file found for %s — removing before start", model_name)
        pid_path.unlink(missing_ok=True)

    log = _log_file(model_name)

    if model_key:
        # Use train_generic.py for multi-model support
        script = Path(settings.scripts_path) / "train_generic.py"
        if not script.exists():
            raise FileNotFoundError(f"Generic training script not found: {script}")
        cmd = [
            "conda", "run", "-n", conda_env,
            "python", str(script),
            "--model", model_key,
            "--run-name", model_name,
            "--epochs", str(epochs),
            "--log-file", log,
        ]
        if resume_checkpoint:
            if not re.match(r"^checkpoint-\d+$", resume_checkpoint):
                raise ValueError(f"Invalid checkpoint name: {resume_checkpoint!r}")
            cp_base = _checkpoint_dir(model_name).resolve()
            full_cp = (cp_base / resume_checkpoint).resolve()
            if not str(full_cp).startswith(str(cp_base)):
                raise ValueError("Checkpoint path escapes checkpoint directory")
            if not full_cp.exists():
                raise FileNotFoundError(f"Checkpoint not found: {full_cp}")
            cmd += ["--resume", str(full_cp)]
    else:
        script = Path(settings.scripts_path) / "train_hime.py"
        if not script.exists():
            raise FileNotFoundError(f"Training script not found: {script}")
        cmd = [
            "conda", "run", "-n", conda_env,
            "python", str(script),
            "--num_train_epochs", str(epochs),
            "--log-file", log,
        ]
        if resume_checkpoint:
            if not re.match(r"^checkpoint-\d+$", resume_checkpoint):
                raise ValueError(f"Invalid checkpoint name: {resume_checkpoint!r}")
            cp_base = _checkpoint_dir(model_name).resolve()
            full_cp = (cp_base / resume_checkpoint).resolve()
            if not str(full_cp).startswith(str(cp_base)):
                raise ValueError("Checkpoint path escapes checkpoint directory")
            if not full_cp.exists():
                raise FileNotFoundError(f"Checkpoint not found: {full_cp}")
            cmd += ["--resume_from_checkpoint", str(full_cp)]

    _log.info("Training command: %s", " ".join(cmd))
    _stderr_fh = open(log, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=_stderr_fh,  # Capture C-level crashes (CUDA, OOM, import errors) to log
    )
    _stderr_fh.close()  # Safe: child process has inherited its own copy of the fd

    meta = {
        "pid": proc.pid,
        "started_at": datetime.now(UTC).isoformat(),
        "checkpoint": resume_checkpoint,
        "log_file": log,
        "epochs": epochs,
    }
    pid_path.write_text(json.dumps(meta), encoding="utf-8")

    return TrainingProcess(model_name=model_name, **meta)  # type: ignore[arg-type]


def stop_training(model_name: str) -> dict:
    _ensure_log_dir()
    pid_path = _pid_file(model_name)
    if not pid_path.exists():
        raise FileNotFoundError(f"No training process found for {model_name}")

    data = json.loads(pid_path.read_text())
    pid = data["pid"]
    _log.info("Stopping training for %s (pid=%d)", model_name, pid)
    graceful = False

    # Step 1: psutil tree kill (most reliable — kills CUDA workers too)
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                _log.info("Killing child process %d (%s)", child.pid, child.name())
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
        gone, alive = psutil.wait_procs([parent] + children, timeout=5)
        if not alive:
            graceful = True
        else:
            _log.warning("%d processes still alive after psutil kill", len(alive))
    except psutil.NoSuchProcess:
        _log.info("Process %d already dead", pid)
        graceful = True
    except Exception as e:
        _log.error("psutil kill failed: %s — falling back to taskkill", e)

    # Step 2: taskkill /F /T fallback (kills entire process tree on Windows)
    if not graceful or _is_process_alive(pid):
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, text=True, timeout=10,
            )
            _log.info("taskkill: %s", result.stdout.strip() or result.stderr.strip())
        except Exception as e:
            _log.error("taskkill failed: %s", e)

    # Step 3: Always clean up PID file
    pid_path.unlink(missing_ok=True)
    _log.info("Deleted PID file for %s", model_name)

    # Step 4: Best-effort CUDA cache clear (non-blocking)
    try:
        subprocess.run(
            ["python", "-c", "import torch; torch.cuda.empty_cache()"],
            timeout=10, capture_output=True,
        )
        _log.info("CUDA cache cleared")
    except Exception as e:
        _log.debug("CUDA cache clear skipped: %s", e)

    return {"stopped": True, "graceful": graceful, "model_name": model_name}


def get_running_processes() -> list[TrainingProcess]:
    _log.debug("Scanning for running training processes")
    _ensure_log_dir()
    log_dir = Path(settings.training_log_path)
    processes = []
    for pid_file in log_dir.glob("*.pid.json"):
        try:
            data = json.loads(pid_file.read_text())
            model_name = pid_file.stem.removesuffix(".pid")
            pid = data["pid"]
            if not _is_process_alive(pid):
                _log.warning(
                    "Stale PID file for %s (pid=%d) — process is dead, cleaning up",
                    model_name, pid,
                )
                pid_file.unlink(missing_ok=True)
                continue
            processes.append(TrainingProcess(model_name=model_name, **data))
        except Exception as e:
            _log.error("Error reading PID file %s: %s — deleting", pid_file, e)
            pid_file.unlink(missing_ok=True)
    return processes


def get_available_checkpoints(model_name: str) -> list[str]:
    cp_dir = _checkpoint_dir(model_name)
    if not cp_dir.exists():
        return []
    names = sorted(
        [d.name for d in cp_dir.iterdir() if d.is_dir() and d.name.startswith("checkpoint-")],
        key=lambda n: int(n.split("-")[-1]) if n.split("-")[-1].isdigit() else 0,
    )
    return names
