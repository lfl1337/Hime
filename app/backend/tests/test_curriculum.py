"""Tests for CurriculumDataLoader and estimate_tier_sizes."""
import json
from pathlib import Path

import pytest

from app.training.curriculum import (
    CurriculumDataLoader,
    Tier,
    estimate_tier_sizes,
)


@pytest.fixture
def jparacrawl_file(tmp_path: Path) -> Path:
    """A small fake jparacrawl jsonl with mixed scores."""
    p = tmp_path / "jparacrawl_500k.jsonl"
    rows = [
        {"input": "JP1", "output": "EN1", "score": 0.95},
        {"input": "JP2", "output": "EN2", "score": 0.80},
        {"input": "JP3", "output": "EN3", "score": 0.65},
        {"input": "JP4", "output": "EN4", "score": 0.58},
        {"input": "JP5", "output": "EN5", "score": 0.40},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


@pytest.fixture
def literary_files(tmp_path: Path) -> list[Path]:
    """Two literary jsonls without scores."""
    a = tmp_path / "shuukura_jp.jsonl"
    a.write_text(json.dumps({"input": "LIT1", "output": "LITEN1"}) + "\n", encoding="utf-8")
    b = tmp_path / "seiyuu_radio_all_jp.jsonl"
    b.write_text(json.dumps({"input": "LIT2", "output": "LITEN2"}) + "\n", encoding="utf-8")
    return [a, b]


class TestCurriculumDataLoader:
    def test_filters_by_score_strict(self, jparacrawl_file, literary_files):
        loader = CurriculumDataLoader(
            source_file=jparacrawl_file,
            literary_files=literary_files,
        )
        ds = loader.load(min_score=0.70)
        # 2 jparacrawl entries (>=0.70) + 2 literary = 4
        assert len(ds) == 4

    def test_filters_by_score_loose(self, jparacrawl_file, literary_files):
        loader = CurriculumDataLoader(
            source_file=jparacrawl_file,
            literary_files=literary_files,
        )
        ds = loader.load(min_score=0.55)
        # 4 jparacrawl entries (>=0.55) + 2 literary = 6
        assert len(ds) == 6

    def test_literary_always_included(self, jparacrawl_file, literary_files):
        loader = CurriculumDataLoader(
            source_file=jparacrawl_file,
            literary_files=literary_files,
        )
        ds = loader.load(min_score=0.99)  # excludes all jparacrawl
        # only 2 literary entries
        assert len(ds) == 2
        outputs = {r["output"] for r in ds}
        assert outputs == {"LITEN1", "LITEN2"}

    def test_cache_returns_same_dataset_object(self, jparacrawl_file, literary_files):
        loader = CurriculumDataLoader(
            source_file=jparacrawl_file,
            literary_files=literary_files,
        )
        ds_a = loader.load(min_score=0.70)
        ds_b = loader.load(min_score=0.70)
        assert ds_a is ds_b

    def test_cache_per_min_score(self, jparacrawl_file, literary_files):
        loader = CurriculumDataLoader(
            source_file=jparacrawl_file,
            literary_files=literary_files,
        )
        ds_a = loader.load(min_score=0.70)
        ds_b = loader.load(min_score=0.55)
        assert ds_a is not ds_b
        assert len(ds_a) < len(ds_b)


class TestEstimateTierSizes:
    def test_returns_size_per_tier(self, jparacrawl_file, literary_files):
        tiers = [
            Tier(name="strict",   min_score=0.70),
            Tier(name="expanded", min_score=0.62),
            Tier(name="loose",    min_score=0.55),
        ]
        sizes = estimate_tier_sizes(jparacrawl_file, tiers, literary_files)
        # strict: 2 jp + 2 lit = 4; expanded: 3 + 2 = 5; loose: 4 + 2 = 6
        assert sizes == {"strict": 4, "expanded": 5, "loose": 6}

    def test_handles_missing_score_field(self, tmp_path, literary_files):
        p = tmp_path / "no_scores.jsonl"
        p.write_text(json.dumps({"input": "X", "output": "Y"}) + "\n", encoding="utf-8")
        tiers = [Tier(name="strict", min_score=0.70)]
        sizes = estimate_tier_sizes(p, tiers, literary_files)
        # missing score → excluded from filtered count, only literary counted
        assert sizes == {"strict": 2}
