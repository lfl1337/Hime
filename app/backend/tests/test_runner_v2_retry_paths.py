"""Phase 4/5/6 — two-path Stage 4 retry integration tests for runner_v2."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.stage4_aggregator import SegmentVerdict
from app.pipeline.stage4_reader import PERSONAS, PersonaAnnotation


@dataclass
class FakeSegment:
    paragraph_id: int
    source_jp: str
    mecab_tokens: list
    glossary_context: str
    rag_context: str


def _ok_annotations(n_sentences: int = 1) -> list[PersonaAnnotation]:
    out: list[PersonaAnnotation] = []
    for sid in range(n_sentences):
        for name, _ in PERSONAS:
            out.append(PersonaAnnotation(persona=name, sentence_id=sid, rating=0.9, issues=[], suggestion=""))
    return out


async def _drain(q: asyncio.Queue) -> list[dict]:
    events: list[dict] = []
    while True:
        item = await q.get()
        if item is None:
            break
        events.append(item)
    return events


def _make_fake_drafts(tag: str = "v1"):
    drafts = MagicMock()
    drafts.qwen32b = f"[{tag}] draft"
    drafts.translategemma12b = None
    drafts.qwen35_9b = None
    drafts.gemma4_e4b = None
    drafts.jmdict = ""
    return drafts


@pytest.fixture
def fake_segment():
    return FakeSegment(
        paragraph_id=42,
        source_jp="彼女は静かに微笑んだ。",
        mecab_tokens=[],
        glossary_context="",
        rag_context="[prior passage] she was smiling",
    )


@pytest.fixture
def patched_pipeline(fake_segment):
    """Patch preprocessor + all stage entrypoints + checkpoint inside runner_v2."""
    import contextlib

    @contextlib.contextmanager
    def _ctx(
        *,
        verdict_sequence: list[SegmentVerdict],
        stage3_outputs: list[str] | None = None,
        stage2_outputs: list[str] | None = None,
        stage1_outputs: list | None = None,
    ):
        stage3_outputs = stage3_outputs or ["polished v1", "polished v2", "polished v3"]
        stage2_outputs = stage2_outputs or ["merged v1", "merged v2"]
        stage1_outputs = stage1_outputs or [_make_fake_drafts("v1"), _make_fake_drafts("v2")]

        stage1_mock = AsyncMock(side_effect=stage1_outputs)
        stage2_mock = AsyncMock(side_effect=stage2_outputs)
        stage3_mock = AsyncMock(side_effect=stage3_outputs)

        reader_mock = MagicMock()
        reader_mock.load = MagicMock()
        reader_mock.unload = MagicMock()
        reader_mock.review = AsyncMock(return_value=_ok_annotations())

        aggregator_mock = MagicMock()
        aggregator_mock.load = MagicMock()
        aggregator_mock.unload = MagicMock()
        aggregator_mock.aggregate_segment = AsyncMock(side_effect=verdict_sequence)

        checkpoint_calls: list[dict] = []
        async def fake_checkpoint(paragraph_id, final_text, confidence_log, **kwargs):
            checkpoint_calls.append({
                "paragraph_id": paragraph_id,
                "final_text": final_text,
                "confidence_log": confidence_log,
                **kwargs,
            })

        async def fake_preprocess(book_id, session):
            return [fake_segment]

        export_mock = AsyncMock(return_value="/tmp/fake.epub")

        with (
            patch("app.pipeline.runner_v2._preprocessor.preprocess_book", fake_preprocess),
            patch("app.pipeline.runner_v2._stage1.run_stage1", stage1_mock),
            patch("app.pipeline.runner_v2._stage2.merge", stage2_mock),
            patch("app.pipeline.runner_v2._stage3.polish", stage3_mock),
            patch("app.pipeline.runner_v2.Stage4Reader", return_value=reader_mock),
            patch("app.pipeline.runner_v2.Stage4Aggregator", return_value=aggregator_mock),
            patch("app.pipeline.runner_v2._checkpoint_segment", side_effect=fake_checkpoint),
            patch("app.pipeline.runner_v2.export_book", export_mock),
        ):
            yield {
                "stage1": stage1_mock,
                "stage2": stage2_mock,
                "stage3": stage3_mock,
                "reader": reader_mock,
                "aggregator": aggregator_mock,
                "checkpoints": checkpoint_calls,
            }

    return _ctx


@pytest.mark.asyncio
async def test_fix_pass_triggers_single_stage3_rerun(patched_pipeline):
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="Tighten dialogue rhythm."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        events = await _drain(q)

    # stage3 is called twice: once initial, once for the fix-pass retry
    assert ctx["stage3"].await_count == 2
    # stage1 and stage2 are called exactly once (no full_retry)
    assert ctx["stage1"].await_count == 1
    assert ctx["stage2"].await_count == 1
    # Stage 3 second call receives the condensed instruction
    second_call = ctx["stage3"].call_args_list[1]
    assert second_call.kwargs.get("retry_instruction") == "Tighten dialogue rhythm."
    # Checkpoint reflects one fix-pass retry
    assert len(ctx["checkpoints"]) == 1
    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 1
    assert cp["retry_count_full_pipeline"] == 0
    assert cp["retry_flag"] is False
    assert cp["aggregator_verdict"] == "ok"
    # WS events include both stage4_verdict transitions
    verdict_events = [e for e in events if e.get("event") == "stage4_verdict"]
    assert len(verdict_events) == 2
    assert verdict_events[0]["verdict"] == "fix_pass"
    assert verdict_events[1]["verdict"] == "ok"
    # VRAM dance: reader + aggregator load/unload once per iteration (2 iters)
    assert ctx["reader"].load.call_count == 2
    assert ctx["reader"].unload.call_count == 2
    assert ctx["aggregator"].load.call_count == 2
    assert ctx["aggregator"].unload.call_count == 2
