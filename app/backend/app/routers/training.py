"""
Training monitor endpoints.

All REST endpoints require X-API-Key header.
The SSE /stream endpoint uses ?api_key= query param because EventSource
cannot send custom headers (same pattern as WebSocket in websocket/streaming.py).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ..auth import require_api_key
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

router = APIRouter(prefix="/training", tags=["training"])


@router.get("/status", response_model=TrainingStatus)
async def training_status(
    run: str = Query(default="Qwen2.5-32B-Instruct"),
    _: str = Depends(require_api_key),
) -> TrainingStatus:
    """Current training run status, step, epoch, and best checkpoint."""
    return get_training_status(run)


@router.get("/checkpoints", response_model=list[CheckpointInfo])
async def list_checkpoints(
    run: str = Query(default="Qwen2.5-32B-Instruct"),
    _: str = Depends(require_api_key),
) -> list[CheckpointInfo]:
    """List all checkpoint directories including the interrupted snapshot."""
    return get_checkpoints(run)


@router.get("/loss-history", response_model=list[LossPoint])
async def loss_history(
    run: str = Query(default="Qwen2.5-32B-Instruct"),
    _: str = Depends(require_api_key),
) -> list[LossPoint]:
    """Full log_history merged by step — training loss and eval loss."""
    return get_loss_history(run)


@router.get("/log")
async def training_log(
    lines: int = Query(default=20, ge=1, le=500),
    run: str = Query(default="Qwen2.5-32B-Instruct"),
    _: str = Depends(require_api_key),
) -> dict:
    """Last N lines of the training log file."""
    return {"lines": get_log_tail(run, lines)}


@router.get("/runs", response_model=list[RunInfo])
async def list_runs(_: str = Depends(require_api_key)) -> list[RunInfo]:
    """List all discovered LoRA training runs with their current status."""
    return get_all_runs()


@router.get("/gguf-models", response_model=list[GGUFModelInfo])
async def list_gguf_models(_: str = Depends(require_api_key)) -> list[GGUFModelInfo]:
    """List all GGUF model directories with size and pipeline role info."""
    return get_gguf_models()


@router.get("/stream")
async def training_stream(
    api_key: str = Query(default=""),
    run: str = Query(default="Qwen2.5-32B-Instruct"),
) -> StreamingResponse:
    """
    SSE stream — emits 'status' and 'log_line' events every 3 seconds.
    Auth via ?api_key= query param (EventSource cannot send headers).
    """
    if api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

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
