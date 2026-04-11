"""Verify Pipeline v2 central config exposes all model IDs and Stage 2/3 use them."""
import inspect

from app.config import pipeline_v2 as cfg
from app.pipeline import stage2_merger, stage3_polish


def test_config_exposes_all_stage_ids():
    ids = cfg.get_all_model_ids()
    expected = {"stage1a", "stage1b", "stage1c", "stage1d", "stage2", "stage3", "stage4_reader", "stage4_aggregator"}
    assert set(ids.keys()) == expected
    for name, value in ids.items():
        assert value, f"{name} is empty"


def test_stage2_uses_central_config():
    """stage2_merger must import its HF ID from config.pipeline_v2."""
    src = inspect.getsource(stage2_merger)
    assert "from ..config.pipeline_v2 import" in src or "from app.config.pipeline_v2 import" in src, (
        "stage2_merger must import from app.config.pipeline_v2"
    )
    hardcoded_count = src.count('"google/translategemma-27b-it"')
    assert hardcoded_count <= 1, f"Too many hardcoded references: {hardcoded_count}"


def test_stage3_uses_central_config():
    src = inspect.getsource(stage3_polish)
    assert "from ..config.pipeline_v2 import" in src or "from app.config.pipeline_v2 import" in src
    hardcoded_count = src.count('"Qwen/Qwen3-30B-A3B"')
    assert hardcoded_count <= 1, f"Too many hardcoded references: {hardcoded_count}"
