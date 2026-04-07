import pytest


class TestModelManagerConfig:
    """Verify model manager reads config correctly."""

    def test_all_six_models_defined(self):
        from app.services.model_manager import PIPELINE_MODELS
        assert len(PIPELINE_MODELS) == 6
        keys = {m["key"] for m in PIPELINE_MODELS}
        assert keys == {"gemma", "deepseek", "qwen32b", "merger", "qwen72b", "qwen14b"}

    def test_model_has_required_fields(self):
        from app.services.model_manager import PIPELINE_MODELS
        for model in PIPELINE_MODELS:
            assert "key" in model
            assert "name" in model
            assert "url_attr" in model
            assert "stage" in model

    def test_get_model_configs_returns_all(self):
        from app.services.model_manager import get_model_configs
        configs = get_model_configs()
        assert len(configs) == 6
        assert all("key" in c and "url" in c for c in configs)
