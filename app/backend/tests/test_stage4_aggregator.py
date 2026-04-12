"""Tests for stage4_aggregator — LFM2-24B-A2B synthesis of 15 reader annotations."""
from __future__ import annotations
import json
from unittest.mock import MagicMock, patch
import pytest


def _make_annotations(rating: float = 0.85) -> list:
    from app.pipeline.stage4_reader import PERSONAS, PersonaAnnotation
    return [
        PersonaAnnotation(persona=name, sentence_id=0, rating=rating, issues=[], suggestion="")
        for name, _ in PERSONAS
    ]


def _make_aggregator_with_output(output_text: str):
    from app.pipeline.stage4_aggregator import Stage4Aggregator
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


@pytest.mark.asyncio
async def test_verdict_okay_when_rating_high():
    from app.pipeline.stage4_aggregator import Stage4Aggregator, AggregatorVerdict
    okay_json = json.dumps({"sentence_id": 0, "verdict": "okay", "retry_instruction": None, "confidence": 0.92})
    agg = _make_aggregator_with_output(okay_json)
    verdict = await agg.aggregate(_make_annotations(rating=0.85))
    assert isinstance(verdict, AggregatorVerdict)
    assert verdict.verdict == "okay"
    assert verdict.retry_instruction is None
    assert 0.0 <= verdict.confidence <= 1.0


@pytest.mark.asyncio
async def test_verdict_retry_when_rating_low():
    from app.pipeline.stage4_aggregator import AggregatorVerdict
    retry_json = json.dumps({"sentence_id": 0, "verdict": "retry", "retry_instruction": "Rewrite to preserve the melancholic undertone.", "confidence": 0.78})
    agg = _make_aggregator_with_output(retry_json)
    verdict = await agg.aggregate(_make_annotations(rating=0.3))
    assert verdict.verdict == "retry"
    assert verdict.retry_instruction is not None
    assert len(verdict.retry_instruction) > 0


@pytest.mark.asyncio
async def test_malformed_output_falls_back_to_okay():
    from app.pipeline.stage4_aggregator import AggregatorVerdict
    agg = _make_aggregator_with_output("THIS IS NOT JSON")
    verdict = await agg.aggregate(_make_annotations(rating=0.5))
    assert isinstance(verdict, AggregatorVerdict)
    assert verdict.verdict == "okay"
    assert verdict.confidence == 0.0


@pytest.mark.asyncio
async def test_aggregate_receives_all_15_personas_in_prompt():
    from app.pipeline.stage4_aggregator import Stage4Aggregator
    from app.pipeline.stage4_reader import PERSONAS
    calls: list[str] = []
    okay_json = json.dumps({"sentence_id": 0, "verdict": "okay", "retry_instruction": None, "confidence": 0.9})
    agg = _make_aggregator_with_output(okay_json)
    original_apply = agg._tokenizer.apply_chat_template
    def capture(messages, **kw):
        calls.extend(messages)
        return original_apply(messages, **kw)
    agg._tokenizer.apply_chat_template = capture
    await agg.aggregate(_make_annotations(rating=0.8))
    combined = " ".join(str(c) for c in calls)
    for name, _ in PERSONAS:
        assert name in combined, f"Persona '{name}' missing from aggregator prompt"


def test_load_model_calls_transformers(monkeypatch):
    import sys
    from unittest.mock import MagicMock
    fake_transformers = MagicMock()
    fake_model = MagicMock()
    fake_tokenizer = MagicMock()
    fake_transformers.AutoModelForCausalLM.from_pretrained.return_value = fake_model
    fake_transformers.AutoTokenizer.from_pretrained.return_value = fake_tokenizer
    fake_transformers.BitsAndBytesConfig.return_value = MagicMock()
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    import importlib
    import app.pipeline.stage4_aggregator as m
    importlib.reload(m)
    from app.config import Settings
    s = Settings()
    agg = m.Stage4Aggregator()
    agg.load(settings=s)
    fake_transformers.AutoModelForCausalLM.from_pretrained.assert_called_once()
