"""Tests for POST-1 fix: pipeline_v2.py reads model IDs from .env, not raw os.environ."""
import sys


def _reload_pipeline_v2():
    """Force reimport of pipeline_v2 to pick up env changes."""
    mods_to_clear = [k for k in sys.modules if "pipeline_v2" in k]
    for m in mods_to_clear:
        del sys.modules[m]
    import app.config.pipeline_v2 as pv2
    return pv2


def test_stage2_model_id_reads_from_env_file(tmp_path, monkeypatch):
    """STAGE2_MODEL_ID must come from .env, not only shell env."""
    env_file = tmp_path / ".env"
    env_file.write_text("HIME_STAGE2_MODEL_ID=test/custom-stage2-model\n", encoding="utf-8")
    monkeypatch.setenv("HIME_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HIME_STAGE2_MODEL_ID", raising=False)

    pv2 = _reload_pipeline_v2()
    assert pv2.STAGE2_MODEL_ID == "test/custom-stage2-model", (
        f"Expected 'test/custom-stage2-model', got {pv2.STAGE2_MODEL_ID!r}"
    )


def test_stage3_model_id_reads_from_env_file(tmp_path, monkeypatch):
    """STAGE3_MODEL_ID must come from .env."""
    env_file = tmp_path / ".env"
    env_file.write_text("HIME_STAGE3_MODEL_ID=test/custom-stage3-model\n", encoding="utf-8")
    monkeypatch.setenv("HIME_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HIME_STAGE3_MODEL_ID", raising=False)

    pv2 = _reload_pipeline_v2()
    assert pv2.STAGE3_MODEL_ID == "test/custom-stage3-model"


def test_defaults_are_set():
    """Without overrides, defaults must be non-empty strings."""
    import app.config.pipeline_v2 as pv2
    assert pv2.STAGE2_MODEL_ID  # not empty
    assert pv2.STAGE3_MODEL_ID
    assert pv2.STAGE1D_MODEL_ID


def test_get_all_model_ids_returns_complete_dict():
    """get_all_model_ids() must return dict with all stage keys."""
    from app.config.pipeline_v2 import get_all_model_ids
    ids = get_all_model_ids()
    required = {"stage1a", "stage1b", "stage1c", "stage1d",
                "stage2", "stage3", "stage4_reader", "stage4_aggregator"}
    assert required <= ids.keys()
    assert all(isinstance(v, str) and v for v in ids.values())
