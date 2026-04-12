"""Regression test for P2-F3: Settings must tolerate extra HIME_* env vars in .env without crashing.

The real failure mode is NOT environment variables in `os.environ`. Pydantic-settings
silently ignores OS env vars that don't map to a declared field — so the bug only
surfaces when `pydantic_settings` parses a `.env` FILE that contains unknown keys.

This test reproduces the Phase 2 crash by writing a `.env` file next to a temp
`HIME_DATA_DIR` with the same 8 undeclared `HIME_*` keys the real project `.env`
contains, then re-importing `app.config` so the Settings class reads that `.env`.

Before the fix: `app.config` raises `pydantic_core.ValidationError` with
`extra_forbidden` on module import.
After the fix (`extra="ignore"`): Settings() succeeds and the unknown keys are
silently dropped — existing declared fields still work.
"""
import importlib
import sys
from pathlib import Path

import pytest

# Register all ORM models with Base.metadata so the session-scoped
# init_db() fixture in conftest.py can run Base.metadata.create_all first.
# Without this, solo-running a test file that never touches models/routers
# leaves Base.metadata empty and init_db()'s ALTER TABLE calls crash with
# "no such table: translations".
import app.models  # noqa: F401


def _reimport_config() -> object:
    """Drop every cached module that depends on app.config, then reimport."""
    for m in list(sys.modules):
        if m == "app.config" or m.startswith("app.config."):
            del sys.modules[m]
    # Also drop downstream consumers that cache settings.db_url at import time;
    # this keeps the test hermetic if something else in the chain already imported
    # app.database above our test. (Not strictly required for this test to prove
    # the fix — the crash happens during `import app.config` — but keeps side
    # effects to a minimum.)
    for m in list(sys.modules):
        if m == "app.database":
            del sys.modules[m]
    return importlib.import_module("app.config")


@pytest.fixture(autouse=True)
def _restore_config_module():
    """Restore app.config and app.database in sys.modules after each test.

    _reimport_config() inside the test evicts app.config while monkeypatch's
    HIME_DATA_DIR override is active. This fixture reimports on teardown, after
    monkeypatch has restored the original env vars, so downstream tests see the
    conftest-correct settings instance.

    Note: do NOT inject monkeypatch here. If this fixture declares monkeypatch
    as a dependency, pytest would tear down monkeypatch AFTER this fixture's
    yield-continuation — meaning the env restore hasn't happened yet when we
    reimport. Without the dependency, monkeypatch (a direct test-fixture dep)
    tears down before this autouse fixture's cleanup, which is the order we need.
    """
    yield  # test runs here; monkeypatch teardown runs first
    # monkeypatch has restored HIME_DATA_DIR by the time we get here
    _reimport_config()


def test_settings_accepts_unknown_env_file_vars(tmp_path, monkeypatch):
    """A .env file containing undeclared HIME_* keys must NOT crash Settings() import."""
    # Recreate the exact 8 undeclared HIME_* vars that the root .env has.
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HIME_PROJECT_ROOT=/tmp/fake\n"
        "HIME_DATA_DIR=/tmp/fake/data\n"
        "HIME_MODELS_DIR=/tmp/fake/modelle\n"
        "HIME_LOGS_DIR=/tmp/fake/logs\n"
        "HIME_EPUB_WATCH_DIR=/tmp/fake/epubs\n"
        "HIME_TRAINING_DATA_DIR=/tmp/fake/training\n"
        "HIME_BIND_HOST=127.0.0.1\n"
        "HIME_BACKEND_PORT=18420\n",
        encoding="utf-8",
    )
    # Point HIME_DATA_DIR at the tmp_path so config.py resolves _ENV_FILE to
    # tmp_path / ".env" (the file we just wrote).
    monkeypatch.setenv("HIME_DATA_DIR", str(tmp_path))

    cfg_mod = _reimport_config()
    # Pre-fix, the import statement above would raise ValidationError. Reaching
    # this line at all proves Settings() tolerates the extra keys.
    assert cfg_mod.settings is not None
    # Sanity: the unknown keys must NOT leak onto the Settings instance as attrs.
    assert not hasattr(cfg_mod.settings, "hime_bind_host")
    assert not hasattr(cfg_mod.settings, "hime_backend_port")


def test_settings_still_reads_declared_env_file_vars(tmp_path, monkeypatch):
    """Declared fields must still be populated from a .env file alongside unknown keys."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PORT=23420\n"
        "HIME_UNKNOWN_VAR=should_be_ignored\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIME_DATA_DIR", str(tmp_path))

    cfg_mod = _reimport_config()
    assert cfg_mod.settings.port == 23420
