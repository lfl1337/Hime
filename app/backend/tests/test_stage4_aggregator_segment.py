"""Phase 3 — segment-level Stage 4 aggregator with severity taxonomy."""
from __future__ import annotations
import json
from unittest.mock import MagicMock
import pytest

from app.pipeline.stage4_aggregator import Stage4Aggregator
from app.pipeline.stage4_reader import PERSONAS, PersonaAnnotation


def _annotations_for_sentences(n_sentences: int, *, rating: float, issues: list[str] | None = None) -> list[PersonaAnnotation]:
    out: list[PersonaAnnotation] = []
    for sid in range(n_sentences):
        for persona, _ in PERSONAS:
            out.append(
                PersonaAnnotation(
                    persona=persona,
                    sentence_id=sid,
                    rating=rating,
                    issues=list(issues or []),
                    suggestion="",
                )
            )
    return out


def _aggregator_with_output(output_text: str) -> Stage4Aggregator:
    agg = Stage4Aggregator.__new__(Stage4Aggregator)
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.return_value = "ENCODED"
    tokenizer.return_value = {"input_ids": [[1, 2, 3]]}
    tokenizer.decode.return_value = output_text
    tokenizer.eos_token_id = 2
    model = MagicMock()
    model.generate.return_value = [[1, 2, 3, 4]]
    model.device = "cuda"
    agg._model = model
    agg._tokenizer = tokenizer
    return agg


def test_segment_verdict_model_has_correct_literal():
    from app.pipeline.stage4_aggregator import SegmentVerdict
    v = SegmentVerdict(verdict="ok", instruction="")
    assert v.verdict == "ok"
    v2 = SegmentVerdict(verdict="fix_pass", instruction="tighten pacing")
    assert v2.verdict == "fix_pass"
    v3 = SegmentVerdict(verdict="full_retry", instruction="rewrite; wrong speaker")
    assert v3.verdict == "full_retry"
    with pytest.raises(Exception):
        SegmentVerdict(verdict="retry", instruction="")  # type: ignore[arg-type]


def test_system_prompt_contains_severity_taxonomy():
    from app.pipeline.stage4_aggregator import _SEGMENT_AGGREGATOR_SYSTEM
    p = _SEGMENT_AGGREGATOR_SYSTEM
    for phrase in ("style", "register", "flow", "punctuation", "honorific"):
        assert phrase in p.lower(), f"light-error trigger '{phrase}' missing from prompt"
    for phrase in ("wrong meaning", "missing", "wrong speaker", "hallucinat", "wrong character name"):
        assert phrase in p.lower(), f"heavy-error trigger '{phrase}' missing from prompt"
    assert '"ok"' in p
    assert '"fix_pass"' in p
    assert '"full_retry"' in p


@pytest.mark.asyncio
async def test_aggregate_segment_ok_verdict():
    from app.pipeline.stage4_aggregator import SegmentVerdict
    out = json.dumps({"verdict": "ok", "instruction": ""})
    agg = _aggregator_with_output(out)
    verdict = await agg.aggregate_segment(_annotations_for_sentences(2, rating=0.9))
    assert isinstance(verdict, SegmentVerdict)
    assert verdict.verdict == "ok"
    assert verdict.instruction == ""


@pytest.mark.asyncio
async def test_aggregate_segment_fix_pass_verdict():
    out = json.dumps({"verdict": "fix_pass", "instruction": "Tighten the dialogue rhythm and use consistent honorifics."})
    agg = _aggregator_with_output(out)
    verdict = await agg.aggregate_segment(_annotations_for_sentences(3, rating=0.4, issues=["awkward flow", "honorific drift"]))
    assert verdict.verdict == "fix_pass"
    assert "honorific" in verdict.instruction.lower()


@pytest.mark.asyncio
async def test_aggregate_segment_full_retry_verdict():
    out = json.dumps({"verdict": "full_retry", "instruction": "Re-translate: speaker attribution is wrong in sentence 1."})
    agg = _aggregator_with_output(out)
    verdict = await agg.aggregate_segment(_annotations_for_sentences(2, rating=0.2, issues=["wrong speaker", "missing clause"]))
    assert verdict.verdict == "full_retry"
    assert "speaker" in verdict.instruction.lower()


@pytest.mark.asyncio
async def test_aggregate_segment_parse_error_falls_back_to_ok():
    agg = _aggregator_with_output("NOT JSON AT ALL")
    verdict = await agg.aggregate_segment(_annotations_for_sentences(1, rating=0.5))
    assert verdict.verdict == "ok"
    assert verdict.instruction == ""


@pytest.mark.asyncio
async def test_aggregate_segment_user_prompt_contains_all_sentences():
    captured: list[str] = []
    out = json.dumps({"verdict": "ok", "instruction": ""})
    agg = _aggregator_with_output(out)

    def capture_apply(messages, **kw):
        for m in messages:
            captured.append(m["content"])
        return "ENCODED"

    agg._tokenizer.apply_chat_template = capture_apply
    await agg.aggregate_segment(_annotations_for_sentences(3, rating=0.8))
    joined = "\n".join(captured)
    assert "Sentence 0" in joined
    assert "Sentence 1" in joined
    assert "Sentence 2" in joined


@pytest.mark.asyncio
async def test_aggregate_segment_empty_annotations_returns_ok():
    from app.pipeline.stage4_aggregator import SegmentVerdict
    agg = _aggregator_with_output(json.dumps({"verdict": "ok", "instruction": ""}))
    verdict = await agg.aggregate_segment([])
    assert isinstance(verdict, SegmentVerdict)
    assert verdict.verdict == "ok"
