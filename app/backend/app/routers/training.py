"""Training monitor endpoints."""
import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Path as FPath, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from ..config import _ENV_FILE, settings
from ..services.training_monitor import (
    CheckpointInfo,
    GGUFModelInfo,
    LossPoint,
    RunInfo,
    TrainingStatus,
    get_all_runs,
    get_checkpoints,
    get_gguf_models,
    get_log_tail,
    get_loss_history,
    get_training_status,
    stream_events,
)
from ..services.training_runner import (
    TrainingProcess,
    get_available_checkpoints,
    get_running_processes,
    start_training,
    stop_training,
)

router = APIRouter(prefix="/training", tags=["training"])


_RUN_PATTERN = r"^[\w\-\.]+$"


class LogResponse(BaseModel):
    lines: list[str]


class CheckpointsResponse(BaseModel):
    checkpoints: list[str]


class StopResponse(BaseModel):
    stopped: bool
    graceful: bool
    model_name: str


class CondaEnvsResponse(BaseModel):
    envs: list[str]


class TrainingConfigPaths(BaseModel):
    models_base_path: str
    lora_path: str
    training_log_path: str
    scripts_path: str


@router.get("/status", response_model=TrainingStatus)
async def training_status(
    run: str = Query(default="Qwen2.5-32B-Instruct", pattern=_RUN_PATTERN, max_length=128),
) -> TrainingStatus:
    """Current training run status, step, epoch, and best checkpoint."""
    return get_training_status(run)


@router.get("/checkpoints", response_model=list[CheckpointInfo])
async def list_checkpoints(
    run: str = Query(default="Qwen2.5-32B-Instruct", pattern=_RUN_PATTERN, max_length=128),
) -> list[CheckpointInfo]:
    """List all checkpoint directories including the interrupted snapshot."""
    return get_checkpoints(run)


@router.get("/loss-history", response_model=list[LossPoint])
async def loss_history(
    run: str = Query(default="Qwen2.5-32B-Instruct", pattern=_RUN_PATTERN, max_length=128),
) -> list[LossPoint]:
    """Full log_history merged by step — training loss and eval loss."""
    return get_loss_history(run)


@router.get("/log", response_model=LogResponse)
async def training_log(
    lines: int = Query(default=20, ge=1, le=500),
    run: str = Query(default="Qwen2.5-32B-Instruct", pattern=_RUN_PATTERN, max_length=128),
) -> LogResponse:
    """Last N lines of the training log file."""
    return LogResponse(lines=get_log_tail(run, lines))


@router.get("/runs", response_model=list[RunInfo])
async def list_runs() -> list[RunInfo]:
    """List all discovered LoRA training runs with their current status."""
    return get_all_runs()


@router.get("/gguf-models", response_model=list[GGUFModelInfo])
async def list_gguf_models() -> list[GGUFModelInfo]:
    """List all GGUF model directories with size and pipeline role info."""
    return get_gguf_models()


@router.get("/stream")
async def training_stream(
    run: str = Query(default="Qwen2.5-32B-Instruct", pattern=_RUN_PATTERN, max_length=128),
) -> StreamingResponse:
    """SSE stream — emits 'status' and 'log_line' events every 3 seconds."""
    async def event_generator():
        async for event in stream_events(run):
            yield f"event: {event['event']}\ndata: {event['data']}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Training process control
# ---------------------------------------------------------------------------

class StartTrainingRequest(BaseModel):
    model_name: str = Field(..., pattern=r"^[\w\-\.]+$", max_length=128)
    resume_checkpoint: str | None = Field(default=None, pattern=r"^checkpoint-\d+$")
    epochs: int = Field(default=3, ge=1, le=100)
    model_key: str | None = Field(default=None, pattern=r"^(qwen32b|qwen14b|qwen72b|gemma27b|deepseek)$")


class StopTrainingRequest(BaseModel):
    model_name: str = Field(..., pattern=r"^[\w\-\.]+$", max_length=128)


@router.post("/start", response_model=TrainingProcess)
async def api_start_training(body: StartTrainingRequest) -> TrainingProcess:
    """Start a training job. Returns 409 if already running, 422 if script/checkpoint missing."""
    try:
        return start_training(
            model_name=body.model_name,
            resume_checkpoint=body.resume_checkpoint,
            epochs=body.epochs,
            model_key=body.model_key,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/stop", response_model=StopResponse)
async def api_stop_training(body: StopTrainingRequest) -> StopResponse:
    """Stop a training job gracefully (CTRL_BREAK → taskkill)."""
    try:
        return stop_training(body.model_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/save-checkpoint")
async def save_checkpoint(
    run: str = Query(..., pattern=_RUN_PATTERN, max_length=128),
) -> dict:
    """Create a SAVE_NOW signal file to trigger immediate checkpoint save."""
    checkpoint_dir = Path(settings.models_base_path) / "lora" / run / "checkpoint"
    if not checkpoint_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint directory not found for run: {run}",
        )
    signal_file = checkpoint_dir / "SAVE_NOW"
    signal_file.touch()
    return {"status": "signal_sent", "run": run}


@router.get("/processes", response_model=list[TrainingProcess])
async def api_get_processes() -> list[TrainingProcess]:
    """List all currently running training processes (auto-cleans dead PIDs)."""
    return get_running_processes()


@router.get("/available-checkpoints/{model_name}", response_model=CheckpointsResponse)
async def api_available_checkpoints(
    model_name: str = FPath(pattern=_RUN_PATTERN, max_length=128),
) -> CheckpointsResponse:
    """List available checkpoint names for a model (for the resume dropdown)."""
    return CheckpointsResponse(checkpoints=get_available_checkpoints(model_name))


_EDITABLE_TRAINING_KEYS = {"models_base_path", "lora_path", "training_log_path", "scripts_path"}


class TrainingConfigUpdate(BaseModel):
    key: str = Field(..., pattern=r"^(models_base_path|lora_path|training_log_path|scripts_path)$")
    value: str = Field(..., max_length=1024)

    @field_validator("value")
    @classmethod
    def _no_dangerous_chars(cls, v: str) -> str:
        if "\x00" in v or "\n" in v or "\r" in v:
            raise ValueError("Invalid characters in value")
        return v


@router.get("/config", response_model=TrainingConfigPaths)
async def training_config() -> TrainingConfigPaths:
    """Read-only backend config values for the Settings page."""
    return TrainingConfigPaths(
        models_base_path=settings.models_base_path,
        lora_path=settings.lora_path,
        training_log_path=settings.training_log_path,
        scripts_path=settings.scripts_path,
    )


@router.post("/config", response_model=TrainingConfigPaths)
async def update_training_config(body: TrainingConfigUpdate) -> TrainingConfigPaths:
    """Update a training config path. Persists to .env and updates in memory."""
    if body.key not in _EDITABLE_TRAINING_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown config key: {body.key}",
        )
    if "\n" in body.value or "\r" in body.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid value: newlines not allowed",
        )
    setattr(settings, body.key, body.value)
    env_path = Path(_ENV_FILE)
    lines: list[str] = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    key_upper = body.key.upper()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key_upper}=") or line.startswith(f"{key_upper} ="):
            lines[i] = f"{key_upper}={body.value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key_upper}={body.value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return TrainingConfigPaths(
        models_base_path=settings.models_base_path,
        lora_path=settings.lora_path,
        training_log_path=settings.training_log_path,
        scripts_path=settings.scripts_path,
    )


_TRAINING_CONFIG_PATH = Path(settings.scripts_path) / "training_config.json"


class TrainingConfig(BaseModel):
    stop_mode: str = "none"
    target_loss: float | None = None
    target_loss_metric: str = "loss"
    target_confirmations: int = 3
    patience: int | None = None
    patience_metric: str = "eval_loss"
    min_delta: float = 0.001
    min_steps: int = 0
    max_epochs: int = 3

    @field_validator('target_loss', 'min_delta', mode='before')
    @classmethod
    def _coerce_float(cls, v: object) -> object:
        if v is None or not isinstance(v, str):
            return v
        try:
            return float(str(v).replace(',', '.'))
        except ValueError:
            raise ValueError(f"Invalid numeric value: {v!r}")

    @field_validator('target_confirmations', 'patience', 'min_steps', 'max_epochs', mode='before')
    @classmethod
    def _coerce_int(cls, v: object) -> object:
        if v is None or not isinstance(v, str):
            return v
        try:
            return int(float(str(v).replace(',', '.')))
        except ValueError:
            raise ValueError(f"Invalid integer value: {v!r}")


@router.get("/stop-config", response_model=TrainingConfig)
async def get_stop_config():
    """Read the smart-stop training configuration from training_config.json."""
    if _TRAINING_CONFIG_PATH.exists():
        with open(_TRAINING_CONFIG_PATH) as f:
            return TrainingConfig(**json.load(f))
    return TrainingConfig()


@router.put("/stop-config", response_model=TrainingConfig)
async def update_stop_config(config: TrainingConfig):
    """Write the smart-stop training configuration to training_config.json."""
    if config.target_loss is not None and config.target_loss <= 0:
        raise HTTPException(status_code=400, detail="target_loss must be > 0")
    if config.patience is not None and config.patience <= 0:
        raise HTTPException(status_code=400, detail="patience must be > 0")
    if config.max_epochs <= 0:
        raise HTTPException(status_code=400, detail="max_epochs must be > 0")
    _TRAINING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_TRAINING_CONFIG_PATH, "w") as f:
        json.dump(config.model_dump(), f, indent=2)
    return config


@router.get("/conda-envs", response_model=CondaEnvsResponse)
async def list_conda_envs() -> CondaEnvsResponse:
    """List available conda environment names."""
    try:
        result = subprocess.run(
            ["conda", "env", "list", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        # Use envs_details[path].name when available (gives "base" not the dir name)
        details: dict = data.get("envs_details", {})
        envs: list[str] = []
        for p in data.get("envs", []):
            name = details.get(p, {}).get("name") or Path(p).name
            envs.append(name)
        return CondaEnvsResponse(envs=envs if envs else ["hime"])
    except Exception:
        return CondaEnvsResponse(envs=["hime"])


@router.get("/backend-log", response_model=LogResponse)
async def backend_log(
    lines: int = Query(default=50, ge=1, le=500),
) -> LogResponse:
    """Last N lines of the backend application log."""
    log_path = Path(settings.backend_log_path)
    if not log_path.exists():
        return LogResponse(lines=[])
    content = log_path.read_text(encoding="utf-8", errors="replace")
    tail = content.splitlines()[-lines:]
    return LogResponse(lines=tail)
