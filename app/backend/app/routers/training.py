"""Training monitor endpoints."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import settings
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


@router.get("/status", response_model=TrainingStatus)
async def training_status(
    run: str = Query(default="Qwen2.5-32B-Instruct"),
) -> TrainingStatus:
    """Current training run status, step, epoch, and best checkpoint."""
    return get_training_status(run)


@router.get("/checkpoints", response_model=list[CheckpointInfo])
async def list_checkpoints(
    run: str = Query(default="Qwen2.5-32B-Instruct"),
) -> list[CheckpointInfo]:
    """List all checkpoint directories including the interrupted snapshot."""
    return get_checkpoints(run)


@router.get("/loss-history", response_model=list[LossPoint])
async def loss_history(
    run: str = Query(default="Qwen2.5-32B-Instruct"),
) -> list[LossPoint]:
    """Full log_history merged by step — training loss and eval loss."""
    return get_loss_history(run)


@router.get("/log")
async def training_log(
    lines: int = Query(default=20, ge=1, le=500),
    run: str = Query(default="Qwen2.5-32B-Instruct"),
) -> dict:
    """Last N lines of the training log file."""
    return {"lines": get_log_tail(run, lines)}


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
    run: str = Query(default="Qwen2.5-32B-Instruct"),
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
    model_name: str
    resume_checkpoint: str | None = None
    epochs: int = 3
    conda_env: str = "hime"


class StopTrainingRequest(BaseModel):
    model_name: str


@router.post("/start", response_model=TrainingProcess)
async def api_start_training(body: StartTrainingRequest) -> TrainingProcess:
    """Start a training job. Returns 409 if already running, 422 if script/checkpoint missing."""
    try:
        return start_training(
            model_name=body.model_name,
            resume_checkpoint=body.resume_checkpoint,
            epochs=body.epochs,
            conda_env=body.conda_env,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/stop")
async def api_stop_training(body: StopTrainingRequest) -> dict:
    """Stop a training job gracefully (CTRL_BREAK → taskkill)."""
    try:
        return stop_training(body.model_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/processes", response_model=list[TrainingProcess])
async def api_get_processes() -> list[TrainingProcess]:
    """List all currently running training processes (auto-cleans dead PIDs)."""
    return get_running_processes()


@router.get("/available-checkpoints/{model_name}")
async def api_available_checkpoints(model_name: str) -> dict:
    """List available checkpoint names for a model (for the resume dropdown)."""
    return {"checkpoints": get_available_checkpoints(model_name)}


@router.get("/backend-log")
async def backend_log(
    lines: int = Query(default=50, ge=1, le=500),
) -> dict:
    """Last N lines of the backend application log."""
    log_path = Path(settings.backend_log_path)
    if not log_path.exists():
        return {"lines": []}
    content = log_path.read_text(encoding="utf-8", errors="replace")
    tail = content.splitlines()[-lines:]
    return {"lines": tail}
