"""
Application settings.

On first run, generates a random API key and writes it to .env so it
persists across restarts. The key is also printed to the console once.

In production Tauri sidecar mode, HIME_DATA_DIR is set by run.py before
this module is imported. When set, .env, hime.db, and logs/ are resolved
relative to that directory instead of beside the source files.
"""
import os
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_HIME_DATA_DIR = os.environ.get("HIME_DATA_DIR")

if _HIME_DATA_DIR:
    _ENV_FILE = Path(_HIME_DATA_DIR) / ".env"
else:
    _ENV_FILE = Path(__file__).parent.parent / ".env"  # dev: app/backend/.env


def _bootstrap_env() -> None:
    """Write API_KEY to .env on first run if missing or empty."""
    env_vars: dict[str, str] = {}

    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()

    if not env_vars.get("API_KEY"):
        key = secrets.token_urlsafe(32)
        env_vars["API_KEY"] = key

        lines = "\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n"
        _ENV_FILE.write_text(lines, encoding="utf-8")

        print(f"\n[hime] Generated API key: {key}")
        print(f"[hime] Saved to: {_ENV_FILE}\n")

        # Make it available in the current process without re-reading the file
        os.environ.setdefault("API_KEY", key)


# Run before Settings is instantiated so pydantic-settings can read it
_bootstrap_env()


class Settings(BaseSettings):
    api_key: str
    port: int = 8000  # preferred port; run.py will scan upward if it's busy
    # Legacy single-model inference (kept for /ws/translate backward compat)
    inference_url: str = "http://127.0.0.1:8080/v1"
    inference_model: str = "qwen2.5-14b-instruct"
    db_url: str = (
        f"sqlite+aiosqlite:///{_HIME_DATA_DIR}/hime.db"
        if _HIME_DATA_DIR
        else "sqlite+aiosqlite:///./hime.db"
    )
    audit_log_path: str = (
        str(Path(_HIME_DATA_DIR) / "logs" / "audit.log")
        if _HIME_DATA_DIR
        else "logs/audit.log"
    )
    rate_limit_per_minute: int = 60

    # Training / fine-tuning paths (override via .env if needed)
    models_base_path: str = r"C:\Projekte\Hime\modelle"
    lora_path: str = r"C:\Projekte\Hime\modelle\lora\Qwen2.5-32B-Instruct"
    training_log_path: str = r"C:\Projekte\Hime\app\backend\logs\training"
    scripts_path: str = r"C:\Projekte\Hime\scripts"

    # Pipeline Stage 1 — three parallel translators
    hime_gemma_url: str = "http://127.0.0.1:8001/v1"
    hime_gemma_model: str = "hime-gemma"
    hime_deepseek_url: str = "http://127.0.0.1:8002/v1"
    hime_deepseek_model: str = "hime-deepseek"
    hime_qwen32b_url: str = "http://127.0.0.1:8003/v1"
    hime_qwen32b_model: str = "hime-qwen32b"

    # Pipeline Consensus — merger model (defaults to qwen32b slot)
    hime_merger_url: str = "http://127.0.0.1:8003/v1"
    hime_merger_model: str = "hime-qwen32b"

    # Pipeline Stage 2 — 72B refinement
    hime_qwen72b_url: str = "http://127.0.0.1:8004/v1"
    hime_qwen72b_model: str = "hime-qwen72b"

    # Pipeline Stage 3 — 14B final polish
    hime_qwen14b_url: str = "http://127.0.0.1:8005/v1"
    hime_qwen14b_model: str = "hime-qwen14b"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
    )


settings = Settings()
