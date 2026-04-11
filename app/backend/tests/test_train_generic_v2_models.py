"""Verify train_generic.py knows Pipeline-v2 models and still supports v1 models (backward compat)."""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def test_v1_models_still_supported():
    """qwen32b, qwen14b, qwen72b, gemma27b, deepseek must remain accessible."""
    src = (SCRIPTS_DIR / "train_generic.py").read_text(encoding="utf-8")
    for key in ("qwen32b", "qwen14b", "qwen72b", "gemma27b", "deepseek"):
        assert f"'{key}'" in src or f'"{key}"' in src, f"v1 model {key} missing"


def test_v2_models_are_added():
    """TranslateGemma-12B, Qwen3.5-9B, Qwen3-30B-A3B must be in train_generic.py."""
    src = (SCRIPTS_DIR / "train_generic.py").read_text(encoding="utf-8")
    for key in ("translategemma12b", "qwen35-9b", "qwen3-30b-a3b"):
        assert f"'{key}'" in src or f'"{key}"' in src, (
            f"Pipeline-v2 model key {key!r} missing from train_generic.py"
        )


def test_training_config_has_curriculum_block():
    """C5: active training_config.json must have a curriculum block with enabled=True."""
    import json
    cfg_path = SCRIPTS_DIR / "training_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "curriculum" in cfg, "training_config.json missing curriculum block"
    assert cfg["curriculum"]["enabled"] is True
    tiers = {t["name"] for t in cfg["curriculum"]["tiers"]}
    assert tiers == {"strict", "expanded", "loose"}, f"Unexpected tiers: {tiers}"
