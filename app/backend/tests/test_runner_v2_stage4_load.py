"""Regression test for C2: runner_v2 must call aggregator.load() before aggregator.aggregate().

This is a source-level check (not a runtime test) because a full-pipeline runtime
test would require the whole model stack. The bug (C2) is a missing line — the
source check catches it cheaply.
"""
from __future__ import annotations

import inspect

from app.pipeline import runner_v2 as runner_mod


def test_runner_v2_source_calls_aggregator_load():
    """run_pipeline_v2 must include `aggregator.load(settings)` in its source."""
    source = inspect.getsource(runner_mod.run_pipeline_v2)
    assert "aggregator.load(settings)" in source, (
        "run_pipeline_v2 must call aggregator.load(settings) before "
        "aggregator.aggregate(). Found source excerpt:\n\n" + source[:2000]
    )
    assert "aggregator.unload()" in source, (
        "Aggregator must also be unloaded in the per-segment loop."
    )


def test_stage4_aggregator_load_unload_symmetry():
    """Every aggregator.load() call should have a matching unload()."""
    source = inspect.getsource(runner_mod.run_pipeline_v2)
    load_count = source.count("aggregator.load(")
    unload_count = source.count("aggregator.unload(")
    assert load_count > 0, "No aggregator.load() calls found"
    assert load_count == unload_count, (
        f"Asymmetric aggregator lifecycle: {load_count} load() vs {unload_count} unload()"
    )
