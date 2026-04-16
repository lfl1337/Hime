"""
Inference server health check endpoint.

DEPRECATED (v2 pipeline): This router calls model_manager.check_all_models(),
which pings HTTP inference servers (llama.cpp, ports 8001–8005). The v2
pipeline uses local Unsloth/Transformers models — no such servers run.
All models will appear offline until this router is rewritten for v2.
See services/model_manager.py for full deprecation context.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..config import settings
from ..services.model_manager import check_all_models

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models() -> list[dict]:
    """
    Check all pipeline inference servers and return online status.
    Uses each server's /v1/models endpoint (OpenAI-compatible).
    Timeout: 2 seconds per server, all checked in parallel.
    """
    return await check_all_models()


class DownloadResponse(BaseModel):
    status: str  # "queued" | "downloading" | "complete"
    message: str


@router.post("/{model_key}/download", response_model=DownloadResponse)
async def request_download(model_key: str) -> DownloadResponse:
    """
    Placeholder: queues a download request. The actual download logic is gated
    behind HIME_ALLOW_DOWNLOADS. When false, returns a queued response with a
    descriptive message.

    W5: Backend-only/CLI — no frontend caller as of v1.1.2; planned for
    model management UI in a future release.
    """
    if not settings.hime_allow_downloads:
        return DownloadResponse(
            status="queued",
            message="Download will start when HIME_ALLOW_DOWNLOADS=true and disk space is available",
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Download manager not yet implemented",
    )
