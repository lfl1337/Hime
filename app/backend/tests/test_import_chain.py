"""Regression tests for W3: isolated module imports must not deadlock on a circular chain.

The original chain was:
  pipeline/__init__.py → runner_v2.py → services/epub_export_service.py
  → pipeline/postprocessor.py → pipeline/__init__.py (loop)

An isolated `import app.services.epub_export_service` triggers the loop because
pipeline/__init__.py eagerly re-exports run_pipeline_v2 from runner_v2.
"""
import importlib
import sys


def _purge(*prefixes: str) -> None:
    """Drop every sys.modules entry that starts with any given prefix."""
    for name in list(sys.modules):
        if any(name == p or name.startswith(p + ".") for p in prefixes):
            del sys.modules[name]


def test_isolated_epub_export_service_import():
    """Importing epub_export_service from a clean state must succeed without cycles."""
    _purge("app.services.epub_export_service", "app.pipeline")
    mod = importlib.import_module("app.services.epub_export_service")
    assert hasattr(mod, "export_book"), "epub_export_service must expose export_book"


def test_isolated_runner_v2_import():
    """Importing runner_v2 from a clean state must succeed."""
    _purge("app.pipeline", "app.services.epub_export_service")
    mod = importlib.import_module("app.pipeline.runner_v2")
    assert hasattr(mod, "run_pipeline_v2"), "runner_v2 must expose run_pipeline_v2"


def test_isolated_pipeline_package_import():
    """Importing the pipeline package directly must succeed."""
    _purge("app.pipeline", "app.services.epub_export_service")
    mod = importlib.import_module("app.pipeline")
    assert mod is not None


def test_full_app_main_import():
    """Full app boot chain must import all routers without error.

    Note: We do NOT purge the ``app`` namespace here because other test files
    (e.g. ``test_paths_v121.py``) hold file-level references to submodules like
    ``app.core.paths`` and call ``importlib.reload()`` on them. A purge would
    remove those entries from ``sys.modules`` and break the later ``reload()``
    calls with "module ... not in sys.modules". Re-importing from a warm cache
    is still a valid sanity check that the router wiring is intact.
    """
    from app.main import app
    assert len(app.routes) >= 60, f"Expected >=60 routes, got {len(app.routes)}"
