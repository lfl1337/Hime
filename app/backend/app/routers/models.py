"""Inference server health check endpoint."""
from fastapi import APIRouter

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
