"""Integration tests for the Stage 4 retry loop inside run_pipeline."""
from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.pipeline.stage4_reader import PersonaAnnotation, PERSONAS
from app.pipeline.stage4_aggregator import AggregatorVerdict


def _okay_annotations(sentence_id: int = 0) -> list[PersonaAnnotation]:
    return [
        PersonaAnnotation(persona=name, sentence_id=sentence_id, rating=0.9, issues=[], suggestion="")
        for name, _ in PERSONAS
    ]


def _retry_annotations(sentence_id: int = 0) -> list[PersonaAnnotation]:
    return [
        PersonaAnnotation(persona=name, sentence_id=sentence_id, rating=0.3, issues=["bad"], suggestion="fix it")
        for name, _ in PERSONAS
    ]


def _okay_verdict(sentence_id: int = 0) -> AggregatorVerdict:
    return AggregatorVerdict(sentence_id=sentence_id, verdict="okay", retry_instruction=None, confidence=0.95)


def _retry_verdict(sentence_id: int = 0) -> AggregatorVerdict:
    return AggregatorVerdict(sentence_id=sentence_id, verdict="retry", retry_instruction="Preserve the wistful tone.", confidence=0.80)


async def _collect_events(ws_queue: asyncio.Queue) -> list[dict]:
    events = []
    while True:
        item = await ws_queue.get()
        if item is None:
            break
        events.append(item)
    return events


def _patch_pipeline(reader_review_return, aggregator_aggregate_return, stage3_output: str = "Stage3 output."):
    import contextlib
    from app.pipeline.stage1 import Stage1Drafts

    @contextlib.asynccontextmanager
    async def _ctx():
        async def aiter_tokens(tokens):
            for t in tokens:
                yield t

        async def fake_checkpoint(*a, **kw):
            pass

        # Build fake Stage1Drafts
        fake_drafts = MagicMock(spec=Stage1Drafts)
        fake_drafts.qwen32b = "Draft output."
        fake_drafts.translategemma12b = None
        fake_drafts.qwen35_9b = None
        fake_drafts.gemma4_e4b = None
        fake_drafts.jmdict = ""

        fake_reader = MagicMock()
        fake_reader.load = MagicMock()
        fake_reader.unload = MagicMock()
        fake_reader.review = AsyncMock(return_value=reader_review_return)

        fake_aggregator = MagicMock()
        fake_aggregator.load = MagicMock()
        fake_aggregator.unload = MagicMock()
        if isinstance(aggregator_aggregate_return, list):
            fake_aggregator.aggregate = AsyncMock(side_effect=aggregator_aggregate_return)
        else:
            fake_aggregator.aggregate = AsyncMock(return_value=aggregator_aggregate_return)

        with (
            patch("app.pipeline.runner.run_stage1", AsyncMock(return_value=fake_drafts)),
            patch("app.pipeline.runner.stream_completion", return_value=aiter_tokens(["out"])),
            patch("app.pipeline.runner._checkpoint", side_effect=fake_checkpoint),
            patch("app.pipeline.runner.Stage4Reader", return_value=fake_reader),
            patch("app.pipeline.runner.Stage4Aggregator", return_value=fake_aggregator),
        ):
            yield fake_reader, fake_aggregator

    return _ctx()


@pytest.mark.asyncio
async def test_stage4_okay_on_first_attempt_no_retry():
    from app.pipeline.runner import run_pipeline
    async with _patch_pipeline(
        reader_review_return=_okay_annotations(),
        aggregator_aggregate_return=_okay_verdict(),
    ) as (reader, aggregator):
        ws_queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline(job_id=1, source_text="彼女は顔を背けた。", notes="", ws_queue=ws_queue)
        events = await _collect_events(ws_queue)
    event_names = [e["event"] for e in events]
    assert "stage4_start" in event_names
    assert "stage4_complete" in event_names
    stage3_completes = [e for e in events if e["event"] == "stage3_complete"]
    assert len(stage3_completes) == 1


@pytest.mark.asyncio
async def test_stage4_retry_triggers_stage3_rerun():
    from app.pipeline.runner import run_pipeline
    verdicts = [_retry_verdict(), _okay_verdict()]
    async with _patch_pipeline(
        reader_review_return=_okay_annotations(),
        aggregator_aggregate_return=verdicts,
    ) as (reader, aggregator):
        ws_queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline(job_id=1, source_text="彼女は顔を背けた。", notes="", ws_queue=ws_queue)
        events = await _collect_events(ws_queue)
    event_names = [e["event"] for e in events]
    assert event_names.count("stage3_complete") == 2
    assert "stage4_retry" in event_names


@pytest.mark.asyncio
async def test_stage4_max_retries_forces_okay():
    from app.pipeline.runner import run_pipeline
    from app.config import settings
    always_retry = [_retry_verdict()] * (settings.stage4_max_retries + 2)
    async with _patch_pipeline(
        reader_review_return=_retry_annotations(),
        aggregator_aggregate_return=always_retry,
    ) as (reader, aggregator):
        ws_queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline(job_id=1, source_text="彼女は顔を背けた。", notes="", ws_queue=ws_queue)
        events = await _collect_events(ws_queue)
    event_names = [e["event"] for e in events]
    assert "pipeline_complete" in event_names
    stage3_completes = [e for e in events if e["event"] == "stage3_complete"]
    assert len(stage3_completes) <= settings.stage4_max_retries + 1


@pytest.mark.asyncio
async def test_stage4_emits_verdict_events():
    from app.pipeline.runner import run_pipeline
    async with _patch_pipeline(
        reader_review_return=_okay_annotations(sentence_id=0),
        aggregator_aggregate_return=_okay_verdict(sentence_id=0),
    ) as _:
        ws_queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline(job_id=1, source_text="彼女は顔を背けた。", notes="", ws_queue=ws_queue)
        events = await _collect_events(ws_queue)
    verdict_events = [e for e in events if e["event"] == "stage4_verdict"]
    assert len(verdict_events) >= 1
    assert "verdict" in verdict_events[0]
