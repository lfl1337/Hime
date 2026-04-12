"""Dry-run model stubs: load/unload are no-ops, generate returns deterministic fake text."""
import pytest

# These imports will fail until Task 4.7 creates dry_run.py
from app.pipeline.dry_run import (
    DryRunModel,
    make_dry_run_stage1_drafts,
    make_dry_run_stage4_reader,
    make_dry_run_stage4_aggregator,
)


class FakeSettings:
    pass


def test_dry_run_model_load_is_noop():
    m = DryRunModel(name="stage2_test")
    m.load(FakeSettings())
    assert m.loaded is True


def test_dry_run_model_unload_is_noop():
    m = DryRunModel(name="stage2_test")
    m.load(FakeSettings())
    m.unload()
    assert m.loaded is False


def test_dry_run_model_generate_is_deterministic():
    m = DryRunModel(name="stage3_test")
    result_a = m.generate("日本語サンプル文 " * 5)
    result_b = m.generate("日本語サンプル文 " * 5)
    assert result_a == result_b
    assert "[DRY-RUN stage3_test]" in result_a


def test_dry_run_model_generate_truncates_prompt_in_output():
    m = DryRunModel(name="s2")
    long_prompt = "x" * 1000
    result = m.generate(long_prompt)
    assert "[DRY-RUN s2]" in result
    assert len(result) < 200


@pytest.mark.asyncio
async def test_dry_run_stage4_reader_returns_annotations():
    reader = make_dry_run_stage4_reader()
    reader.load(FakeSettings())
    out = await reader.review(sentences=["Hello world."], source_sentences=["こんにちは世界。"])
    assert len(out) == 15  # 15 personas × 1 sentence
    for ann in out:
        assert 0.0 <= ann.rating <= 1.0
        assert ann.sentence_id == 0
    reader.unload()


@pytest.mark.asyncio
async def test_dry_run_stage4_aggregator_returns_verdict():
    aggregator = make_dry_run_stage4_aggregator()
    aggregator.load(FakeSettings())
    reader = make_dry_run_stage4_reader()
    reader.load(FakeSettings())
    annotations = await reader.review(sentences=["Hi."], source_sentences=["こんにちは。"])
    verdict = await aggregator.aggregate(annotations)
    assert verdict.verdict in ("okay", "retry")
    assert 0.0 <= verdict.confidence <= 1.0
    aggregator.unload()
    reader.unload()


@pytest.mark.asyncio
async def test_dry_run_stage1_drafts_shape():
    drafts = await make_dry_run_stage1_drafts(
        segment="テスト",
        rag_context="",
        glossary_context="",
    )
    assert hasattr(drafts, "qwen32b")
    assert hasattr(drafts, "translategemma12b")
    assert hasattr(drafts, "qwen35_9b")
    assert hasattr(drafts, "llm_jp")
    assert hasattr(drafts, "jmdict")
    for name in ("qwen32b", "translategemma12b", "qwen35_9b", "llm_jp"):
        val = getattr(drafts, name)
        assert "[DRY-RUN" in val, f"{name} should contain DRY-RUN marker"
