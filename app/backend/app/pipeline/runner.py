"""
Multi-stage translation pipeline orchestrator — v2.

Pipeline stages:
  Stage 1 — 5 independent drafts in parallel (stage1/ package):
              1A  Qwen2.5-32B LoRA (Ollama)
              1B  TranslateGemma-12B (Unsloth local)
              1C  Qwen3.5-9B non-thinking (Unsloth local)
              1D  Gemma4 E4B GGUF (Unsloth local)
              1E  JMdict literal gloss (LexiconService, always succeeds)
  Consensus — merger model synthesises a single best translation
  Stage 2   — 72B model refines the consensus
  Stage 3   — 14B model does a final polish → final_output

Each stage streams tokens to ``ws_queue`` as JSON-serialisable dicts.
DB checkpoints are written after every stage via short-lived AsyncSessionLocal
sessions so the job survives a WebSocket disconnect.
"""
import asyncio
import json
import re
import time

from sqlalchemy import select

import logging as _logging

from ..config import settings
from ..database import AsyncSessionLocal
from ..inference import stream_completion
from ..models import Book, Translation
from .prompts import (
    consensus_messages,
    stage2_messages,
    stage3_messages,
)
from .stage1 import run_stage1, Stage1Drafts
from .stage4_reader import Stage4Reader
from .stage4_aggregator import Stage4Aggregator


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


_CONFIDENCE_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _log_safe(msg: str, exc: BaseException) -> None:
    _logging.getLogger(__name__).warning("[pipeline] %s: %s", msg, exc)


def _parse_confidence_log(text: str) -> dict | None:
    """Extract the confidence JSON block from a consensus output."""
    if not text:
        return None
    m = _CONFIDENCE_FENCE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "confidence" not in data:
        return None
    return data


async def _checkpoint(job_id: int, **fields) -> None:
    """Write arbitrary column updates to a Translation row.

    Non-fatal: any DB error is logged as a warning and swallowed so that a
    checkpoint failure never aborts the pipeline.
    """
    try:
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
    except Exception as exc:
        _logging.getLogger(__name__).warning(
            "checkpoint write failed for job %s: %s", job_id, exc
        )


def _drafts_to_stage1_outputs(drafts: Stage1Drafts) -> dict[str, str]:
    """
    Convert Stage1Drafts to the dict format expected by consensus_messages().
    Only non-None, non-empty fields are included. jmdict is always included
    if non-empty (it's the completeness anchor).
    """
    out: dict[str, str] = {}
    if drafts.qwen32b:
        out["qwen32b"] = drafts.qwen32b
    if drafts.translategemma12b:
        out["translategemma12b"] = drafts.translategemma12b
    if drafts.qwen35_9b:
        out["qwen35_9b"] = drafts.qwen35_9b
    if drafts.gemma4_e4b:
        out["gemma4_e4b"] = drafts.gemma4_e4b
    out["jmdict"] = drafts.jmdict  # always include, even if empty
    return out


async def run_pipeline(
    job_id: int,
    source_text: str,
    notes: str,
    ws_queue: asyncio.Queue,
    book_id: int | None = None,
) -> None:
    """
    Full pipeline coroutine.  Designed to run as an asyncio.Task so that a
    WebSocket disconnect does not abort in-flight inference calls.
    """
    started_at = time.monotonic()
    glossary_block = ""
    rag_context_block = ""

    # ------------------------------------------------------------------ #
    # v2 enrichment — glossary, RAG context                               #
    # Lexicon anchor is now handled inside adapter_jmdict.py (Stage 1E). #
    # All fetches are best-effort; failure → empty string (no crash)      #
    # ------------------------------------------------------------------ #
    if book_id is not None:
        try:
            from ..services.glossary_service import GlossaryService
            async with AsyncSessionLocal() as session:
                svc = GlossaryService(session)
                g = await svc.get_or_create_for_book(book_id)
                glossary_block = await svc.format_for_prompt(g.id, source_text)
        except Exception as exc:  # noqa: BLE001
            _log_safe("glossary fetch failed", exc)

        try:
            from ..rag.retriever import format_rag_context, retrieve_top_k
            async with AsyncSessionLocal() as session:
                book = await session.get(Book, book_id)
            if book is not None and book.series_id is not None:
                chunks = await retrieve_top_k(book.series_id, source_text, top_k=5)
                rag_context_block = format_rag_context(chunks)
        except Exception as exc:  # noqa: BLE001
            _log_safe("rag retrieval failed", exc)

    try:
        # ------------------------------------------------------------------ #
        # Stage 1 — 5 adapters (4 neural + 1 lexical)                        #
        # ------------------------------------------------------------------ #
        adapter_names = ["qwen32b", "translategemma12b", "qwen35_9b", "gemma4_e4b", "jmdict"]
        await ws_queue.put({"event": "stage1_start", "models": adapter_names})
        await _checkpoint(job_id, current_stage="stage1")

        drafts = await run_stage1(
            segment=source_text,
            rag_context=rag_context_block,
            glossary_context=glossary_block,
            notes=notes,
        )

        stage1_outputs = _drafts_to_stage1_outputs(drafts)

        # Emit per-adapter completion events for the frontend
        for label, text in stage1_outputs.items():
            await ws_queue.put({"event": "stage1_complete", "model": label, "output": text})

        # Notify frontend about unavailable adapters
        for label in adapter_names:
            if label not in stage1_outputs:
                await ws_queue.put({
                    "event": "model_unavailable",
                    "model": label,
                    "reason": "Adapter failed or returned empty output",
                })

        if not stage1_outputs:
            await ws_queue.put({
                "event": "pipeline_error",
                "detail": "No Stage 1 adapters succeeded — cannot continue pipeline",
            })
            await _checkpoint(job_id, current_stage="error")
            return

        await _checkpoint(
            job_id,
            stage1_gemma_output=drafts.translategemma12b,
            stage1_deepseek_output=drafts.qwen35_9b,
            stage1_qwen32b_output=drafts.qwen32b,
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

        # v1.2.1: parse confidence log from consensus output
        confidence_data = _parse_confidence_log(consensus_text)
        if confidence_data is not None:
            await _checkpoint(job_id, confidence_log=json.dumps(confidence_data))
            await ws_queue.put({"event": "confidence_log", "data": confidence_data})

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

        # ------------------------------------------------------------------ #
        # Stage 4 — Reader Panel + Aggregator (retry loop, max N attempts)   #
        # ------------------------------------------------------------------ #
        import re as _re
        _SENT_SPLIT = _re.compile(r'(?<=[.!?…」])\s+')
        sentences = _SENT_SPLIT.split(final_text.strip()) or [final_text]
        source_sentences = _SENT_SPLIT.split(source_text.strip()) or [source_text]
        if len(source_sentences) < len(sentences):
            source_sentences += [source_sentences[-1]] * (len(sentences) - len(source_sentences))
        source_sentences = source_sentences[: len(sentences)]

        reader = Stage4Reader()
        reader.load(settings)
        aggregator = Stage4Aggregator()

        attempt = 0
        max_attempts = settings.stage4_max_retries + 1

        while attempt < max_attempts:
            attempt += 1
            await ws_queue.put({"event": "stage4_start", "attempt": attempt})
            await _checkpoint(job_id, current_stage=f"stage4_attempt_{attempt}")

            annotations = await reader.review(sentences=sentences, source_sentences=source_sentences)
            await ws_queue.put({"event": "stage4_reader_complete", "attempt": attempt, "annotation_count": len(annotations)})

            reader.unload()
            aggregator.load(settings)

            from itertools import groupby as _groupby
            sorted_ann = sorted(annotations, key=lambda a: a.sentence_id)
            verdicts: list = []
            for sid, group in _groupby(sorted_ann, key=lambda a: a.sentence_id):
                verdict = await aggregator.aggregate(list(group))
                verdicts.append(verdict)
                await ws_queue.put({
                    "event": "stage4_verdict",
                    "attempt": attempt,
                    "sentence_id": sid,
                    "verdict": verdict.verdict,
                    "retry_instruction": verdict.retry_instruction,
                    "confidence": verdict.confidence,
                })

            aggregator.unload()

            retry_verdicts = [v for v in verdicts if v.verdict == "retry"]
            if not retry_verdicts or attempt >= max_attempts:
                if retry_verdicts and attempt >= max_attempts:
                    await ws_queue.put({"event": "stage4_forced_okay", "attempt": attempt, "detail": "Max retries reached; accepting current translation."})
                break

            retry_notes = " | ".join(
                f"[s{v.sentence_id}] {v.retry_instruction}"
                for v in retry_verdicts
                if v.retry_instruction
            )
            await ws_queue.put({"event": "stage4_retry", "attempt": attempt, "retry_notes": retry_notes})

            await ws_queue.put({"event": "stage3_start"})
            await _checkpoint(job_id, current_stage=f"stage3_retry_{attempt}")

            final_text = await _stream_stage(
                "stage3",
                settings.hime_qwen14b_url,
                settings.hime_qwen14b_model,
                stage3_messages(stage2_text, retry_notes=retry_notes),
                ws_queue,
            )
            await _checkpoint(job_id, final_output=final_text)

            sentences = _SENT_SPLIT.split(final_text.strip()) or [final_text]
            if len(source_sentences) < len(sentences):
                source_sentences += [source_sentences[-1]] * (len(sentences) - len(source_sentences))
            source_sentences = source_sentences[: len(sentences)]

            reader.load(settings)

        await ws_queue.put({"event": "stage4_complete", "attempts": attempt, "final_output": final_text})

        duration_ms = int((time.monotonic() - started_at) * 1000)
        await _checkpoint(job_id, final_output=final_text, content=final_text, current_stage="complete", pipeline_duration_ms=duration_ms)
        await ws_queue.put({"event": "pipeline_complete", "final_output": final_text, "duration_ms": duration_ms})

    except Exception as exc:
        await ws_queue.put({"event": "pipeline_error", "detail": str(exc)})
        await _checkpoint(job_id, current_stage="error")

    finally:
        # Sentinel: tells the drain loop that the pipeline is done
        await ws_queue.put(None)
