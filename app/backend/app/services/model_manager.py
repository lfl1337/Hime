"""
Model endpoint manager — health checks and configuration for all pipeline models.

Reads model URLs from app.config.settings (which reads from .env).
Provides async health checks for individual models and batch status.
"""
import asyncio
import logging
import time

import httpx

from ..config import settings

_log = logging.getLogger(__name__)

# All 6 pipeline models with their config attribute names and pipeline stage
PIPELINE_MODELS = [
    {"key": "gemma",    "name": "Gemma 3 12B",     "url_attr": "hime_gemma_url",    "model_attr": "hime_gemma_model",    "stage": "stage1"},
    {"key": "deepseek", "name": "DeepSeek R1 32B",  "url_attr": "hime_deepseek_url", "model_attr": "hime_deepseek_model", "stage": "stage1"},
    {"key": "qwen32b",  "name": "Qwen 2.5 32B",     "url_attr": "hime_qwen32b_url",  "model_attr": "hime_qwen32b_model",  "stage": "stage1"},
    {"key": "merger",   "name": "Merger (Qwen 32B)", "url_attr": "hime_merger_url",   "model_attr": "hime_merger_model",   "stage": "consensus"},
    {"key": "qwen72b",  "name": "Qwen 2.5 72B",     "url_attr": "hime_qwen72b_url",  "model_attr": "hime_qwen72b_model",  "stage": "stage2"},
    {"key": "qwen14b",  "name": "Qwen 2.5 14B",     "url_attr": "hime_qwen14b_url",  "model_attr": "hime_qwen14b_model",  "stage": "stage3"},
]


def get_model_configs() -> list[dict]:
    """Return all pipeline model configs with their current URLs."""
    result = []
    for m in PIPELINE_MODELS:
        result.append({
            "key": m["key"],
            "name": m["name"],
            "url": getattr(settings, m["url_attr"]),
            "model": getattr(settings, m["model_attr"]),
            "stage": m["stage"],
        })
    return result


async def check_model_health(key: str) -> dict:
    """
    Ping a single model's /v1/models endpoint.
    Returns: {"key", "name", "endpoint", "online", "loaded_model", "latency_ms"}
    """
    model_def = next((m for m in PIPELINE_MODELS if m["key"] == key), None)
    if model_def is None:
        return {"key": key, "name": "Unknown", "endpoint": "", "online": False, "loaded_model": None, "latency_ms": None}

    url = getattr(settings, model_def["url_attr"])
    name = model_def["name"]
    t0 = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{url}/models")
            latency_ms = round((time.monotonic() - t0) * 1000)
            online = r.status_code < 500
            loaded_model = None
            if online:
                data = r.json()
                models_list = data.get("data", [])
                if models_list:
                    loaded_model = models_list[0].get("id")
            return {
                "key": key,
                "name": name,
                "endpoint": url,
                "online": online,
                "loaded_model": loaded_model,
                "latency_ms": latency_ms,
            }
    except Exception:
        return {
            "key": key,
            "name": name,
            "endpoint": url,
            "online": False,
            "loaded_model": None,
            "latency_ms": None,
        }


async def check_all_models() -> list[dict]:
    """Check health of all 6 pipeline models in parallel."""
    tasks = [check_model_health(m["key"]) for m in PIPELINE_MODELS]
    return list(await asyncio.gather(*tasks))
