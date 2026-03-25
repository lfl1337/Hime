"""Inference server health check endpoint."""
import httpx
from fastapi import APIRouter

from ..config import settings

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models() -> list[dict]:
    """
    Check each Stage-1 inference server and return online status.
    Uses llama.cpp's /v1/models endpoint (OpenAI-compatible).
    Timeout: 2 seconds per server.
    """
    endpoints = [
        {"key": "gemma",    "name": "Gemma 3 27B",    "url": settings.hime_gemma_url},
        {"key": "deepseek", "name": "DeepSeek R1 32B", "url": settings.hime_deepseek_url},
        {"key": "qwen32b",  "name": "Qwen 2.5 32B",    "url": settings.hime_qwen32b_url},
    ]
    results = []
    async with httpx.AsyncClient(timeout=2.0) as client:
        for ep in endpoints:
            try:
                r = await client.get(f"{ep['url']}/models")
                online = r.status_code < 500
                loaded_model = None
                if online:
                    data = r.json()
                    models_list = data.get("data", [])
                    if models_list:
                        loaded_model = models_list[0].get("id")
            except Exception:
                online = False
                loaded_model = None
            results.append({
                "key": ep["key"],
                "name": ep["name"],
                "endpoint": ep["url"],
                "online": online,
                "loaded_model": loaded_model,
            })
    return results
