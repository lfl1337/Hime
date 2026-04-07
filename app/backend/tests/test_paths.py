import os
from pathlib import Path

import pytest


class TestPaths:
    """Verify centralized path resolution."""

    def test_project_root_exists(self):
        from app.core.paths import PROJECT_ROOT
        assert PROJECT_ROOT.exists()

    def test_project_root_contains_app_dir(self):
        from app.core.paths import PROJECT_ROOT
        assert (PROJECT_ROOT / "app").exists()

    def test_models_dir_derived_from_root(self):
        from app.core.paths import PROJECT_ROOT, MODELS_DIR
        assert str(MODELS_DIR).startswith(str(PROJECT_ROOT))

    def test_env_override(self, monkeypatch, tmp_path):
        """HIME_PROJECT_ROOT env var overrides default."""
        monkeypatch.setenv("HIME_PROJECT_ROOT", str(tmp_path))
        import importlib
        from app.core import paths
        importlib.reload(paths)
        assert paths.PROJECT_ROOT == tmp_path
        monkeypatch.delenv("HIME_PROJECT_ROOT")
        importlib.reload(paths)

    def test_checkpoints_dir(self):
        from app.core.paths import checkpoints_dir, MODELS_DIR
        result = checkpoints_dir("Qwen2.5-32B-Instruct")
        assert "Qwen2.5-32B-Instruct" in str(result)
        assert "checkpoint" in str(result)

    def test_no_hardcoded_c_drive(self):
        """Ensure no C: drive paths in the module source."""
        from app.core import paths
        import inspect
        source = inspect.getsource(paths)
        assert "C:\\" not in source
        assert "C:/" not in source
