"""
WebSocket endpoints for live token streaming.

Legacy single-model endpoint (backward compat):
    ws://127.0.0.1:8000/ws/translate

New multi-stage pipeline endpoint:
    ws://127.0.0.1:8000/ws/translate/{job_id}

Close codes:
    4004 — Job not found
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..inference import translate_stream
from ..models import Translation
from ..pipeline.runner import run_pipeline
from ..utils.sanitize import sanitize_text

router = APIRouter(tags=["websocket"])

# Tracks in-flight pipeline tasks keyed by job_id to prevent double-spawning
_active_pipelines: dict[int, asyncio.Task] = {}


@router.websocket("/ws/translate")
async def ws_translate(websocket: WebSocket) -> None:
    await websocket.accept()

    from ..config import settings

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON payload"})
                continue

            text: str = data.get("text", "")
            model: str = data.get("model", "") or settings.inference_model
            notes: str = data.get("notes", "") or ""

            # Sanitize before passing to the local model
            try:
                text = sanitize_text(text, "text")
                if notes:
                    notes = sanitize_text(notes, "notes")
            except Exception as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                continue

            # Stream tokens from the local inference server to the frontend
            try:
                async for token in translate_stream(text=text, model=model, notes=notes):
                    await websocket.send_json({"type": "token", "content": token})
            except Exception as exc:
                await websocket.send_json({
                    "type": "error",
                    "detail": f"Inference error: {exc}",
                })
                continue

            await websocket.send_json({"type": "done", "model": model})

    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# New pipeline WebSocket: /ws/translate/{job_id}
# ---------------------------------------------------------------------------

@router.websocket("/ws/translate/{job_id}")
async def ws_translate_pipeline(
    websocket: WebSocket,
    job_id: int,
) -> None:
    """
    Pipeline WebSocket for a specific translation job.

    - If the pipeline is not yet started, spawn it as a background task.
    - If the pipeline is already running (reconnect), attach to the queue.
    - If the job is already complete, emit pipeline_complete and close.
    """
    # Load job row
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Translation).where(Translation.id == job_id)
        )
        job: Optional[Translation] = result.scalar_one_or_none()

    if job is None:
        await websocket.close(code=4004, reason="Job not found")
        return

    await websocket.accept()

    # Already complete — replay final state and close
    if job.current_stage == "complete":
        await websocket.send_json({
            "event": "pipeline_complete",
            "final_output": job.final_output or "",
            "duration_ms": job.pipeline_duration_ms or 0,
        })
        await websocket.close()
        return

    # Attach a queue; spawn the pipeline task if not already running
    ws_queue: asyncio.Queue = asyncio.Queue()

    if job_id not in _active_pipelines or _active_pipelines[job_id].done():
        # Fetch source text content for pipeline
        async with AsyncSessionLocal() as session:
            src_result = await session.execute(
                select(Translation).where(Translation.id == job_id)
            )
            job_row: Optional[Translation] = src_result.scalar_one_or_none()
            if job_row is None:
                await websocket.send_json({"event": "pipeline_error", "detail": "Job not found"})
                await websocket.close()
                return

            from ..models import SourceText
            source_result = await session.execute(
                select(SourceText).where(SourceText.id == job_row.source_text_id)
            )
            source = source_result.scalar_one_or_none()
            if source is None:
                await websocket.send_json({"event": "pipeline_error", "detail": "Source text not found"})
                await websocket.close()
                return

            source_content = source.content
            notes = job_row.notes or ""

        task = asyncio.create_task(
            run_pipeline(job_id, source_content, notes, ws_queue)
        )
        _active_pipelines[job_id] = task
    else:
        # Pipeline already running — reconnect path.
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Translation).where(Translation.id == job_id)
            )
            current_job = result.scalar_one_or_none()
        if current_job:
            await websocket.send_json({
                "event": "pipeline_status",
                "current_stage": current_job.current_stage,
            })

        # Wait for the running task to finish, then emit the completion event
        task = _active_pipelines[job_id]
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=600)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Translation).where(Translation.id == job_id)
            )
            finished_job = result.scalar_one_or_none()
        if finished_job and finished_job.current_stage == "complete":
            await websocket.send_json({
                "event": "pipeline_complete",
                "final_output": finished_job.final_output or "",
                "duration_ms": finished_job.pipeline_duration_ms or 0,
            })
        elif finished_job:
            await websocket.send_json({
                "event": "pipeline_error",
                "detail": f"Pipeline ended in stage: {finished_job.current_stage}",
            })
        try:
            await websocket.close()
        except Exception:
            pass
        return

    # Drain queue → WebSocket until pipeline sends None sentinel or client disconnects
    try:
        while True:
            event = await ws_queue.get()
            if event is None:
                # Pipeline finished; clean up and close
                _active_pipelines.pop(job_id, None)
                break
            await websocket.send_json(event)
    except WebSocketDisconnect:
        # Client disconnected — pipeline task continues running in background
        pass
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
