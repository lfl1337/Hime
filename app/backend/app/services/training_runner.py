"""Start/stop LoRA training jobs from the app UI."""
import ctypes
import ctypes.wintypes
import json
import logging
import re
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import psutil
from pydantic import BaseModel

from ..config import settings

_log = logging.getLogger(__name__)


# Windows Job Object — ensures child processes die when parent dies
_job_handle = None

def _create_job_object():
    """Create a Windows Job Object with KILL_ON_JOB_CLOSE flag."""
    global _job_handle
    if sys.platform != "win32" or _job_handle is not None:
        return
    try:
        kernel32 = ctypes.windll.kernel32

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            _log.warning("Failed to create Job Object")
            return

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.wintypes.DWORD),
                ("SchedulingClass", ctypes.wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [("i", ctypes.c_uint64)] * 6

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(
            job, 9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info), ctypes.sizeof(info),
        )
        _job_handle = job
        _log.info("Windows Job Object created for child process management")
    except Exception as e:
        _log.warning("Job Object creation failed: %s", e)


def _assign_to_job(proc) -> None:
    """Assign a subprocess to the Job Object so it dies with the parent."""
    if _job_handle is None or sys.platform != "win32":
        return
    try:
        handle = int(proc._handle)  # Windows process handle
        ctypes.windll.kernel32.AssignProcessToJobObject(_job_handle, handle)
        _log.debug("Assigned PID %d to Job Object", proc.pid)
    except Exception as e:
        _log.warning("Failed to assign PID %d to Job Object: %s", proc.pid, e)


# Initialize Job Object on module load
_create_job_object()


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

    # Append smart stopping args from training_config.json
    _cfg_path = Path(settings.scripts_path) / "training_config.json"
    if _cfg_path.exists():
        try:
            import json as _json
            with open(_cfg_path) as _cf:
                _cfg = _json.load(_cf)
            if _cfg.get("target_loss") is not None:
                val = float(_cfg["target_loss"])
                if val > 0:
                    cmd += ["--target-loss", str(val)]
            if _cfg.get("patience") is not None:
                val = int(_cfg["patience"])
                if val > 0:
                    cmd += ["--patience", str(val)]
            if _cfg.get("min_delta") is not None:
                cmd += ["--min-delta", str(float(_cfg["min_delta"]))]
            if _cfg.get("min_steps"):
                cmd += ["--min-steps", str(int(_cfg["min_steps"]))]
            if _cfg.get("max_epochs") is not None and _cfg["max_epochs"] != 3:
                val = int(_cfg["max_epochs"])
                if val > 0:
                    cmd += ["--max-epochs", str(val)]
        except Exception:
            pass  # never crash training start on config read failure

    _log.info("Training command: %s", " ".join(cmd))
    with open(log, "a", encoding="utf-8") as _stderr_fh:
        proc = subprocess.Popen(
            cmd,
            creationflags=0,
            stdout=subprocess.DEVNULL,
            stderr=_stderr_fh,  # Capture C-level crashes (CUDA, OOM, import errors) to log
        )
    # Parent-Handle geschlossen; Child-Kopie des FD bleibt offen
    _assign_to_job(proc)

    import time as _time
    _audit_log = logging.getLogger("hime.audit")
    _audit_log.info(json.dumps({
        "ts": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        "event": "subprocess_start",
        "model_name": model_name,
        "pid": proc.pid,
        "command": cmd,
        "epochs": epochs,
        "checkpoint": resume_checkpoint,
    }, ensure_ascii=False))

    max_duration = 72 * 3600
    meta = {
        "pid": proc.pid,
        "started_at": datetime.now(UTC).isoformat(),
        "checkpoint": resume_checkpoint,
        "log_file": log,
        "epochs": epochs,
        "max_duration_seconds": max_duration,
    }
    pid_path.write_text(json.dumps(meta), encoding="utf-8")

    return TrainingProcess(model_name=model_name, **meta)  # type: ignore[arg-type]


def _kill_survivors(all_pids: list[int], model_name: str) -> None:
    """Post-stop check at +5s: kill any PIDs from the training tree that are still alive."""
    import time
    time.sleep(5)
    survivors = [p for p in all_pids if psutil.pid_exists(p)]
    if not survivors:
        _log.info("Post-stop check OK — all %d PIDs dead for %s", len(all_pids), model_name)
        return
    _log.warning(
        "Post-stop check: %d survivor(s) still alive for %s — PIDs %s — force-killing",
        len(survivors), model_name, survivors,
    )
    for p in survivors:
        try:
            psutil.Process(p).kill()
            _log.info("Post-stop killed PID %d", p)
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            _log.error("Post-stop kill failed for PID %d: %s", p, e)


def stop_training(model_name: str) -> dict:
    _ensure_log_dir()
    pid_path = _pid_file(model_name)
    if not pid_path.exists():
        raise FileNotFoundError(f"No training process found for {model_name}")

    data = json.loads(pid_path.read_text())
    pid = data["pid"]
    _log.info("Stopping training for %s (pid=%d)", model_name, pid)
    graceful = False

    # Step 1: collect the full process tree before killing anything
    # (once the parent dies its children may become orphans and disappear from the tree)
    all_pids: list[int] = [pid]
    procs_to_wait: list[psutil.Process] = []
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        all_pids.extend(c.pid for c in children)
        _log.info(
            "Process tree for %s: parent=%d, children=%s",
            model_name, pid, [c.pid for c in children],
        )
        procs_to_wait = [parent] + children

        # Step 2: kill children first, then kill parent explicitly
        for child in children:
            try:
                _log.info("Killing child PID %d (%s)", child.pid, child.name())
                child.kill()
            except psutil.NoSuchProcess:
                pass
        try:
            _log.info("Killing parent PID %d", pid)
            parent.kill()
        except psutil.NoSuchProcess:
            pass

        # Step 3: wait up to 5 s for the whole tree to die
        gone, alive = psutil.wait_procs(procs_to_wait, timeout=5)
        if not alive:
            graceful = True
        else:
            _log.warning(
                "%d process(es) still alive after psutil kill: %s",
                len(alive), [p.pid for p in alive],
            )

    except psutil.NoSuchProcess:
        _log.info("Process %d already dead", pid)
        graceful = True
    except Exception as e:
        _log.error("psutil kill failed: %s — falling back to taskkill", e)

    # Step 4: taskkill /F /T for each PID that is still alive
    # (targets every known PID individually so orphaned children are caught too)
    still_alive = [p for p in all_pids if psutil.pid_exists(p)]
    if still_alive:
        for p in still_alive:
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(p)],
                    capture_output=True, text=True, timeout=10,
                )
                _log.info("taskkill PID %d: %s", p, result.stdout.strip() or result.stderr.strip())
            except Exception as e:
                _log.error("taskkill failed for PID %d: %s", p, e)

    # Step 5: verify ALL known PIDs are gone
    surviving = [p for p in all_pids if psutil.pid_exists(p)]
    if surviving:
        _log.warning("After stop: %d PID(s) still exist: %s", len(surviving), surviving)
    else:
        _log.info("Verified: all %d PID(s) dead for %s", len(all_pids), model_name)
        graceful = True

    # Step 6: schedule post-stop survivor check at +5 s
    threading.Thread(target=_kill_survivors, args=(all_pids, model_name), daemon=True).start()

    # Step 7: always clean up PID file
    pid_path.unlink(missing_ok=True)
    _log.info("Deleted PID file for %s", model_name)

    # Step 8: best-effort CUDA cache clear (non-blocking)
    try:
        subprocess.run(
            ["python", "-c", "import torch; torch.cuda.empty_cache()"],
            timeout=10, capture_output=True,
        )
        _log.info("CUDA cache cleared")
    except Exception as e:
        _log.debug("CUDA cache clear skipped: %s", e)

    import time as _time
    _audit_log = logging.getLogger("hime.audit")
    _audit_log.info(json.dumps({
        "ts": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        "event": "subprocess_stop",
        "model_name": model_name,
    }, ensure_ascii=False))

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
            # Enforce max duration timeout
            max_dur = data.get("max_duration_seconds", 72 * 3600)
            started = datetime.fromisoformat(data["started_at"])
            elapsed = (datetime.now(UTC) - started).total_seconds()
            if elapsed > max_dur:
                _log.warning(
                    "Training %s exceeded max duration (%.0fh > %.0fh) — killing",
                    model_name, elapsed / 3600, max_dur / 3600,
                )
                try:
                    stop_training(model_name)
                except Exception as e:
                    _log.error("Failed to stop timed-out training %s: %s", model_name, e)
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
