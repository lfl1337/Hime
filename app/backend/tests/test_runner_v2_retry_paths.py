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


@pytest.mark.asyncio
async def test_full_retry_triggers_stage1_to_stage3_rerun(patched_pipeline, fake_segment):
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="full_retry", instruction="Re-translate: speaker wrong in sentence 1."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        events = await _drain(q)

    # Stage 1 and Stage 2 each run TWICE: once originally, once for full-retry
    assert ctx["stage1"].await_count == 2
    assert ctx["stage2"].await_count == 2
    assert ctx["stage3"].await_count == 2

    # Contract: runner_v2 must call run_stage1 with rag_context as a kwarg
    assert "rag_context" in ctx["stage1"].call_args_list[1].kwargs, (
        "run_stage1 must be called with rag_context as a keyword argument"
    )
    rag_ctx = ctx["stage1"].call_args_list[1].kwargs["rag_context"]
    assert "Retry instruction from prior review" in rag_ctx
    assert "speaker wrong" in rag_ctx
    # Original rag_context is preserved
    assert "prior passage" in rag_ctx

    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 0
    assert cp["retry_count_full_pipeline"] == 1
    assert cp["retry_flag"] is False
    assert cp["aggregator_verdict"] == "ok"

    # WS events include the re-emitted stage events for the second pass
    stage1_completes = [e for e in events if e.get("event") == "stage1_complete"]
    stage2_completes = [e for e in events if e.get("event") == "stage2_complete"]
    stage3_completes = [e for e in events if e.get("event") == "stage3_complete"]
    assert len(stage1_completes) == 2
    assert len(stage2_completes) == 2
    assert len(stage3_completes) == 2
    # The second set of stage events is tagged retry_kind="full_retry"
    assert any(e.get("retry_kind") == "full_retry" for e in stage1_completes)
    assert any(e.get("retry_kind") == "full_retry" for e in stage2_completes)
    assert any(e.get("retry_kind") == "full_retry" for e in stage3_completes)


@pytest.mark.asyncio
async def test_full_retry_then_fix_pass_uses_both_budgets(patched_pipeline):
    """A full_retry that gets re-judged as fix_pass consumes one of each budget."""
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="full_retry", instruction="Re-translate: missing clause."),
        SegmentVerdict(verdict="fix_pass", instruction="Clean up punctuation."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        await _drain(q)

    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 1
    assert cp["retry_count_full_pipeline"] == 1
    assert cp["retry_flag"] is False


@pytest.mark.asyncio
async def test_fix_pass_exhaustion_sets_retry_flag(patched_pipeline):
    """After 2 failed fix_pass retries the segment emits with retry_flag=True."""
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="Fix A"),
        SegmentVerdict(verdict="fix_pass", instruction="Fix B"),
        SegmentVerdict(verdict="fix_pass", instruction="Fix C"),  # budget exhausted
    ]
    with patched_pipeline(
        verdict_sequence=verdicts,
        stage3_outputs=["polished v1", "polished v2", "polished v3"],
    ) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        events = await _drain(q)

    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 2  # MAX_FIX_PASS_RETRIES
    assert cp["retry_count_full_pipeline"] == 0
    assert cp["retry_flag"] is True
    # Pipeline completes normally — segment is not blocked
    event_names = [e["event"] for e in events]
    assert "segment_complete" in event_names
    assert "pipeline_complete" in event_names
    seg_complete = next(e for e in events if e["event"] == "segment_complete")
    assert seg_complete["retry_flag"] is True
    # reviewer_notes stamped with exhaustion reason
    assert cp.get("reviewer_notes") is not None
    assert "retry budget exhausted" in cp["reviewer_notes"].lower()
    assert "Fix C" in cp["reviewer_notes"]


@pytest.mark.asyncio
async def test_full_retry_exhaustion_sets_retry_flag(patched_pipeline):
    """After 1 failed full_retry the segment emits with retry_flag=True."""
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="full_retry", instruction="Fix wrong speaker"),
        SegmentVerdict(verdict="full_retry", instruction="Still wrong"),  # budget exhausted
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        await _drain(q)

    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 0
    assert cp["retry_count_full_pipeline"] == 1  # MAX_FULL_PIPELINE_RETRIES
    assert cp["retry_flag"] is True
    # reviewer_notes gets stamped explaining the exhaustion
    assert cp.get("reviewer_notes") is not None
    assert "retry budget exhausted" in cp["reviewer_notes"].lower()
    assert "Still wrong" in cp["reviewer_notes"]


@pytest.mark.asyncio
async def test_retry_flag_not_set_when_budget_not_exhausted(patched_pipeline):
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="small fix"),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        await _drain(q)

    cp = ctx["checkpoints"][0]
    assert cp["retry_flag"] is False
