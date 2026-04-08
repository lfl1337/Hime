"""
Curriculum data loader for tiered training.

Loads jparacrawl_500k.jsonl on the fly, filters by score, merges in literary
sources unconditionally, and returns a HuggingFace `datasets.Dataset` object.

Tier definitions and source paths are passed in by the caller (the training
script reads them from `training_config.json`'s curriculum section).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from datasets import Dataset


@dataclass(frozen=True)
class Tier:
    name: str
    min_score: float


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _filter_jparacrawl(source_file: Path, min_score: float) -> list[dict]:
    rows: list[dict] = []
    for entry in _iter_jsonl(source_file):
        score = entry.get("score")
        if score is None:
            continue
        if float(score) >= min_score:
            rows.append(entry)
    return rows


def _load_literary(literary_files: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in literary_files:
        if not path.exists():
            continue
        rows.extend(_iter_jsonl(path))
    return rows


class CurriculumDataLoader:
    """
    Loads tiered training data on demand. Caches each tier in memory keyed by
    `min_score` so repeated loads (e.g. on resume) don't re-scan disk.
    """

    def __init__(self, source_file: Path, literary_files: list[Path]) -> None:
        self.source_file = Path(source_file)
        self.literary_files = [Path(p) for p in literary_files]
        self._cache: dict[float, Dataset] = {}

    def load(self, min_score: float) -> Dataset:
        key = round(float(min_score), 4)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        filtered = _filter_jparacrawl(self.source_file, key)
        literary = _load_literary(self.literary_files)
        merged = filtered + literary
        ds = Dataset.from_list(merged)
        self._cache[key] = ds
        return ds


def estimate_tier_sizes(
    source_file: Path,
    tiers: list[Tier],
    literary_files: list[Path],
) -> dict[str, int]:
    """
    Quickly count how many samples each tier would yield. Used at training start
    to print a sanity-check banner before tokenization.
    """
    literary_count = sum(1 for p in literary_files if p.exists() for _ in _iter_jsonl(p))

    sizes: dict[str, int] = {}
    counts_by_threshold: dict[float, int] = {}
    thresholds = sorted({round(t.min_score, 4) for t in tiers})

    # Single pass over the source file: bucket each entry by lowest threshold it satisfies
    for threshold in thresholds:
        counts_by_threshold[threshold] = 0
    for entry in _iter_jsonl(source_file):
        score = entry.get("score")
        if score is None:
            continue
        score_f = float(score)
        for threshold in thresholds:
            if score_f >= threshold:
                counts_by_threshold[threshold] += 1

    for tier in tiers:
        key = round(tier.min_score, 4)
        sizes[tier.name] = counts_by_threshold.get(key, 0) + literary_count
    return sizes
