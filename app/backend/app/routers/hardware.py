"""Hardware monitoring endpoints."""
import asyncio
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..services.hardware_monitor import (
    HardwareStats,
    get_hardware_history,
    get_hardware_stats,
)

router = APIRouter(prefix="/hardware", tags=["hardware"])


@router.get("/stats", response_model=HardwareStats)
async def hardware_stats() -> HardwareStats:
    """Current GPU/CPU/RAM hardware stats."""
    return await asyncio.to_thread(get_hardware_stats)


@router.get("/history", response_model=list[HardwareStats])
async def hardware_history(
    minutes: int = Query(default=10, ge=1, le=60),
) -> list[HardwareStats]:
    """Hardware stats history for the last N minutes (from SQLite)."""
    return await asyncio.to_thread(get_hardware_history, minutes)


@router.get("/stream")
async def hardware_stream() -> StreamingResponse:
    """SSE stream — emits 'hardware_stats' events every 5 seconds, skipping no-op events."""
    async def event_generator():
        prev_vram: int | None = None
        prev_gpu_util: int | None = None
        prev_temp: int | None = None
        while True:
            try:
                stats = await asyncio.to_thread(get_hardware_stats)
                vram = stats.gpu_vram_used_mb or 0
                gpu  = stats.gpu_utilization_pct or 0
                temp = stats.gpu_temp_celsius or 0
                changed = (
                    prev_vram is None
                    or abs(vram - prev_vram) >= 100
                    or abs(gpu  - prev_gpu_util) >= 1
                    or abs(temp - prev_temp) >= 1
                )
                if changed:
                    prev_vram, prev_gpu_util, prev_temp = vram, gpu, temp
                    yield f"event: hardware_stats\ndata: {stats.model_dump_json()}\n\n"
            except Exception:
                pass
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
