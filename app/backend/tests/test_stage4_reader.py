"""
Tests for stage4_reader — 15-persona local Qwen3.5-2B reader panel.
Model is fully mocked.
"""
from __future__ import annotations
import asyncio
import json
from unittest.mock import MagicMock, patch
import pytest

_GOOD_JSON = json.dumps({
    "persona": "Purist",
    "sentence_id": 0,
    "rating": 0.9,
    "issues": [],
    "suggestion": "",
})

def _make_fake_model_and_tokenizer(output_text: str = _GOOD_JSON):
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.return_value = "ENCODED_PROMPT"
    tokenizer.return_value = {"input_ids": [[1, 2, 3]]}
    tokenizer.decode.return_value = output_text
    tokenizer.eos_token_id = 2
    model = MagicMock()
    model.generate.return_value = [[1, 2, 3, 4]]
    model.device = "cuda"
    return model, tokenizer

@pytest.mark.asyncio
async def test_review_returns_15_annotations_for_one_sentence():
    from app.pipeline.stage4_reader import Stage4Reader, PersonaAnnotation
    model, tokenizer = _make_fake_model_and_tokenizer()
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer
    sentences = ["She turned away."]
    annotations = await reader.review(sentences=sentences, source_sentences=["彼女は顔を背けた。"])
    assert len(annotations) == 15
    assert all(isinstance(a, PersonaAnnotation) for a in annotations)

@pytest.mark.asyncio
async def test_each_annotation_has_correct_fields():
    from app.pipeline.stage4_reader import Stage4Reader, PersonaAnnotation
    model, tokenizer = _make_fake_model_and_tokenizer()
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer
    annotations = await reader.review(sentences=["She turned away."], source_sentences=["彼女は顔を背けた。"])
    a = annotations[0]
    assert isinstance(a.persona, str) and len(a.persona) > 0
    assert isinstance(a.sentence_id, int)
    assert 0.0 <= a.rating <= 1.0
    assert isinstance(a.issues, list)
    assert isinstance(a.suggestion, str)

@pytest.mark.asyncio
async def test_malformed_model_output_does_not_crash():
    from app.pipeline.stage4_reader import Stage4Reader
    model, tokenizer = _make_fake_model_and_tokenizer("NOT JSON AT ALL")
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer
    annotations = await reader.review(sentences=["test"], source_sentences=["テスト"])
    assert all(a.rating == 0.5 for a in annotations)
    assert all("parse_error" in a.issues for a in annotations)

@pytest.mark.asyncio
async def test_review_multi_sentence_returns_15_per_sentence():
    from app.pipeline.stage4_reader import Stage4Reader
    model, tokenizer = _make_fake_model_and_tokenizer()
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer
    sentences = ["Sentence one.", "Sentence two.", "Sentence three."]
    annotations = await reader.review(sentences=sentences, source_sentences=["一。", "二。", "三。"])
    assert len(annotations) == 15 * 3

@pytest.mark.asyncio
async def test_all_15_persona_names_appear():
    from app.pipeline.stage4_reader import Stage4Reader, PERSONAS
    model, tokenizer = _make_fake_model_and_tokenizer()
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer
    annotations = await reader.review(sentences=["x"], source_sentences=["x"])
    found_personas = {a.persona for a in annotations}
    expected_personas = {p[0] for p in PERSONAS}
    assert found_personas == expected_personas

def test_load_model_calls_unsloth(monkeypatch):
    import sys
    fake_unsloth = MagicMock()
    fake_model = MagicMock()
    fake_tokenizer = MagicMock()
    fake_unsloth.FastLanguageModel.from_pretrained.return_value = (fake_model, fake_tokenizer)
    monkeypatch.setitem(sys.modules, "unsloth", fake_unsloth)
    import importlib
    import app.pipeline.stage4_reader as m
    importlib.reload(m)
    from app.config import Settings
    s = Settings()
    reader = m.Stage4Reader()
    reader.load(settings=s)
    fake_unsloth.FastLanguageModel.from_pretrained.assert_called_once()
    call_kwargs = fake_unsloth.FastLanguageModel.from_pretrained.call_args
    assert call_kwargs.kwargs.get("load_in_4bit") is True or call_kwargs[1].get("load_in_4bit") is True
