"""
Multi-stage translation pipeline orchestrator.

Pipeline stages:
  Stage 1 — three models translate in parallel (gemma, deepseek, qwen32b)
  Consensus — merger model synthesises a single best translation
  Stage 2 — 72B model refines the consensus
  Stage 3 — 14B model does a final polish → final_output

Each stage streams tokens to ``ws_queue`` as JSON-serialisable dicts.
DB checkpoints are written after every stage via short-lived AsyncSessionLocal
sessions so the job survives a WebSocket disconnect.
"""
import asyncio
import time

from sqlalchemy import select

from ..config import settings
from ..database import AsyncSessionLocal
from ..inference import stream_completion
from ..models import Translation
from .prompts import (
    consensus_messages,
    stage1_messages,
    stage2_messages,
    stage3_messages,
)


async def _stream_stage1(
    label: str,
    url: str,
    model: str,
    messages: list[dict[str, str]],
    ws_queue: asyncio.Queue,
) -> tuple[str, str]:
    """
    Stream a single Stage-1 model, enqueuing tokens as they arrive.
    Returns ``(label, full_output)``.
    Raises on connection/inference error — caller uses return_exceptions=True.
    """
    buf: list[str] = []
    async for token in stream_completion(url, model, messages):
        buf.append(token)
        await ws_queue.put({"event": "stage1_token", "model": label, "token": token})
    full = "".join(buf)
    await ws_queue.put({"event": "stage1_complete", "model": label, "output": full})
    return label, full


async def _stream_stage(
    event_prefix: str,
    url: str,
    model: str,
    messages: list[dict[str, str]],
    ws_queue: asyncio.Queue,
) -> str:
    """
    Generic streaming helper for consensus / stage2 / stage3.
    Enqueues ``{event_prefix}_token`` and ``{event_prefix}_complete`` events.
    Returns the full output string.
    """
    buf: list[str] = []
    async for token in stream_completion(url, model, messages):
        buf.append(token)
        await ws_queue.put({"event": f"{event_prefix}_token", "token": token})
    full = "".join(buf)
    await ws_queue.put({"event": f"{event_prefix}_complete", "output": full})
    return full


async def _checkpoint(job_id: int, **fields) -> None:
    """Write arbitrary column updates to a Translation row."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Translation).where(Translation.id == job_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        for k, v in fields.items():
            setattr(row, k, v)
        await session.commit()


async def run_pipeline(
    job_id: int,
    source_text: str,
    notes: str,
    ws_queue: asyncio.Queue,
) -> None:
    """
    Full pipeline coroutine.  Designed to run as an asyncio.Task so that a
    WebSocket disconnect does not abort in-flight inference calls.
    """
    started_at = time.monotonic()

    try:
        # ------------------------------------------------------------------ #
        # Stage 1 — three models in parallel                                  #
        # ------------------------------------------------------------------ #
        await ws_queue.put({"event": "stage1_start", "models": ["gemma", "deepseek", "qwen32b"]})
        await _checkpoint(job_id, current_stage="stage1")

        msgs = stage1_messages(source_text, notes)
        results = await asyncio.gather(
            _stream_stage1("gemma",    settings.hime_gemma_url,    settings.hime_gemma_model,    msgs, ws_queue),
            _stream_stage1("deepseek", settings.hime_deepseek_url, settings.hime_deepseek_model, msgs, ws_queue),
            _stream_stage1("qwen32b",  settings.hime_qwen32b_url,  settings.hime_qwen32b_model,  msgs, ws_queue),
            return_exceptions=True,
        )

        stage1_labels = ["gemma", "deepseek", "qwen32b"]
        stage1_outputs: dict[str, str] = {}
        for idx, res in enumerate(results):
            label = stage1_labels[idx]
            if isinstance(res, BaseException):
                await ws_queue.put({
                    "event": "model_error",
                    "stage": "stage1",
                    "model": label,
                    "detail": str(res),
                })
            else:
                _, text = res
                if text.strip():
                    stage1_outputs[label] = text
                else:
                    await ws_queue.put({
                        "event": "model_error",
                        "stage": "stage1",
                        "model": label,
                        "detail": "Empty output",
                    })

        # Notify frontend about unavailable models
        for label in stage1_labels:
            if label not in stage1_outputs:
                await ws_queue.put({
                    "event": "model_unavailable",
                    "model": label,
                    "reason": "Model failed or returned empty output",
                })

        if not stage1_outputs:
            await ws_queue.put({
                "event": "pipeline_error",
                "detail": "No Stage 1 models succeeded — cannot continue pipeline",
            })
            await _checkpoint(job_id, current_stage="error")
            return

        await _checkpoint(
            job_id,
            stage1_gemma_output=stage1_outputs.get("gemma"),
            stage1_deepseek_output=stage1_outputs.get("deepseek"),
            stage1_qwen32b_output=stage1_outputs.get("qwen32b"),
        )

        # ------------------------------------------------------------------ #
        # Consensus                                                            #
        # ------------------------------------------------------------------ #
        await ws_queue.put({"event": "consensus_start"})
        await _checkpoint(job_id, current_stage="consensus")

        consensus_text = await _stream_stage(
            "consensus",
            settings.hime_merger_url,
            settings.hime_merger_model,
            consensus_messages(source_text, stage1_outputs),
            ws_queue,
        )
        await _checkpoint(job_id, consensus_output=consensus_text)

        # ------------------------------------------------------------------ #
        # Stage 2 — 72B refinement                                            #
        # ------------------------------------------------------------------ #
        await ws_queue.put({"event": "stage2_start"})
        await _checkpoint(job_id, current_stage="stage2")

        stage2_text = await _stream_stage(
            "stage2",
            settings.hime_qwen72b_url,
            settings.hime_qwen72b_model,
            stage2_messages(consensus_text),
            ws_queue,
        )
        await _checkpoint(job_id, stage2_output=stage2_text)

        # ------------------------------------------------------------------ #
        # Stage 3 — 14B final polish                                          #
        # ------------------------------------------------------------------ #
        await ws_queue.put({"event": "stage3_start"})
        await _checkpoint(job_id, current_stage="stage3")

        final_text = await _stream_stage(
            "stage3",
            settings.hime_qwen14b_url,
            settings.hime_qwen14b_model,
            stage3_messages(stage2_text),
            ws_queue,
        )

        duration_ms = int((time.monotonic() - started_at) * 1000)
        await _checkpoint(
            job_id,
            final_output=final_text,
            content=final_text,
            current_stage="complete",
            pipeline_duration_ms=duration_ms,
        )

        await ws_queue.put({
            "event": "pipeline_complete",
            "final_output": final_text,
            "duration_ms": duration_ms,
        })

    except Exception as exc:
        await ws_queue.put({"event": "pipeline_error", "detail": str(exc)})
        await _checkpoint(job_id, current_stage="error")

    finally:
        # Sentinel: tells the drain loop that the pipeline is done
        await ws_queue.put(None)
