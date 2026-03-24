"""Start/stop LoRA training jobs from the app UI."""
import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil
from pydantic import BaseModel

from ..config import settings


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


def _is_alive(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        return proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def start_training(
    model_name: str,
    resume_checkpoint: str | None = None,
    epochs: int = 3,
    conda_env: str = "hime",
) -> TrainingProcess:
    pid_path = _pid_file(model_name)
    if pid_path.exists():
        data = json.loads(pid_path.read_text())
        if _is_alive(data["pid"]):
            raise RuntimeError(f"Training already running for {model_name} (PID {data['pid']})")

    script = Path(settings.scripts_path) / "train_hime.py"
    if not script.exists():
        raise FileNotFoundError(f"Training script not found: {script}")

    log = _log_file(model_name)
    cmd = [
        "conda", "run", "-n", conda_env,
        "python", str(script),
        "--num_train_epochs", str(epochs),
        "--log-file", log,
    ]

    if resume_checkpoint:
        full_cp = _checkpoint_dir(model_name) / resume_checkpoint
        if not full_cp.exists():
            raise FileNotFoundError(f"Checkpoint not found: {full_cp}")
        cmd += ["--resume_from_checkpoint", str(full_cp)]

    proc = subprocess.Popen(
        cmd,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

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
    pid_path = _pid_file(model_name)
    if not pid_path.exists():
        raise FileNotFoundError(f"No running training process for {model_name}")

    data = json.loads(pid_path.read_text())
    pid = data["pid"]
    graceful = False

    if _is_alive(pid):
        # Send CTRL_BREAK — triggers HuggingFace Trainer to save checkpoint
        try:
            os.kill(pid, signal.CTRL_BREAK_EVENT)
            for _ in range(30):
                time.sleep(1)
                if not _is_alive(pid):
                    graceful = True
                    break
        except OSError:
            pass

        if not graceful and _is_alive(pid):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)

    pid_path.unlink(missing_ok=True)
    return {"stopped": True, "graceful": graceful}


def get_running_processes() -> list[TrainingProcess]:
    log_dir = Path(settings.training_log_path)
    processes = []
    for pid_file in log_dir.glob("*.pid.json"):
        try:
            data = json.loads(pid_file.read_text())
            model_name = pid_file.stem.removesuffix(".pid")
            if _is_alive(data["pid"]):
                processes.append(TrainingProcess(model_name=model_name, **data))
            else:
                pid_file.unlink(missing_ok=True)  # clean up dead PID files
        except Exception:
            pass
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
