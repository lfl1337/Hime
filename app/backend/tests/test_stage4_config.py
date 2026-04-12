"""Tests for Stage 4 settings in config."""

def test_stage4_reader_model_id_has_default():
    from app.config import Settings
    from app.core import paths as _paths
    s = Settings()
    # Default points to local model path resolved from MODELS_DIR
    assert s.stage4_reader_model_id == str(_paths.MODELS_DIR / "qwen3.5-2b")

def test_stage4_aggregator_model_id_has_default():
    from app.config import Settings
    from app.core import paths as _paths
    s = Settings()
    # Default points to local model path resolved from MODELS_DIR
    assert s.stage4_aggregator_model_id == str(_paths.MODELS_DIR / "lfm2-24b")

def test_stage4_max_retries_default_is_3():
    from app.config import Settings
    s = Settings()
    assert s.stage4_max_retries == 3

def test_stage4_reader_dtype_default():
    from app.config import Settings
    s = Settings()
    assert s.stage4_reader_dtype == "nf4"

def test_stage4_aggregator_dtype_default():
    from app.config import Settings
    s = Settings()
    assert s.stage4_aggregator_dtype == "int4"
