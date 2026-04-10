"""
Application settings.

In production Tauri sidecar mode, HIME_DATA_DIR is set by run.py before
this module is imported. When set, .env, hime.db, and logs/ are resolved
relative to that directory instead of beside the source files.
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .core import paths as _paths

_HIME_DATA_DIR = os.environ.get("HIME_DATA_DIR")

if _HIME_DATA_DIR:
    _ENV_FILE = Path(_HIME_DATA_DIR) / ".env"
else:
    _ENV_FILE = Path(__file__).parent.parent / ".env"  # dev: app/backend/.env


class Settings(BaseSettings):
    port: int = 18420  # Hime-specific range (18420-18519) — avoids collision with other local apps
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
    backend_log_path: str = (
        str(Path(_HIME_DATA_DIR) / "logs" / "hime-backend.log")
        if _HIME_DATA_DIR
        else "logs/hime-backend.log"
    )
    rate_limit_per_minute: int = 60
    epub_watch_folder_default: str = str(_paths.EPUB_WATCH_DIR)

    # Training / fine-tuning paths (override via .env if needed)
    models_base_path: str = str(_paths.MODELS_DIR)
    lora_path: str = str(_paths.lora_dir("Qwen2.5-32B-Instruct"))
    training_log_path: str = str(_paths.TRAINING_LOG_DIR)
    scripts_path: str = str(_paths.SCRIPTS_DIR)

    # Pipeline Stage 1 — three parallel translators
    hime_gemma_url: str = "http://127.0.0.1:8001/v1"
    hime_gemma_model: str = "hime-gemma"
    hime_deepseek_url: str = "http://127.0.0.1:8002/v1"
    hime_deepseek_model: str = "hime-deepseek"
    hime_qwen32b_url: str = "http://127.0.0.1:8003/v1"
    hime_qwen32b_model: str = "hime-qwen32b"

    # Pipeline Stage 1 v2 — local Unsloth model paths (relative to MODELS_DIR by default)
    # Override via .env: HIME_TRANSLATEGEMMA_PATH=/absolute/path/to/model
    # NOTE: unsloth requires separate install: pip install "unsloth[cu124-torch260]"
    hime_translategemma_path: str = ""   # resolved at runtime → MODELS_DIR/translategemma-12b
    hime_qwen35_9b_path: str = ""        # resolved at runtime → MODELS_DIR/qwen3.5-9b
    hime_gemma4_path: str = ""           # resolved at runtime → MODELS_DIR/gemma4-e4b

    # Pipeline Consensus — merger model (defaults to qwen32b slot)
    hime_merger_url: str = "http://127.0.0.1:8003/v1"
    hime_merger_model: str = "hime-qwen32b"

    # Pipeline Stage 2 — 72B refinement
    hime_qwen72b_url: str = "http://127.0.0.1:8004/v1"
    hime_qwen72b_model: str = "hime-qwen72b"

    # Pipeline Stage 3 — 14B final polish
    hime_qwen14b_url: str = "http://127.0.0.1:8005/v1"
    hime_qwen14b_model: str = "hime-qwen14b"

    # Reader/Critic Panel — 6 persona reviewers (all default to qwen14b slot)
    hime_reader_model: str = "hime-qwen14b"
    hime_reader_names_url: str = ""
    hime_reader_register_url: str = ""
    hime_reader_omissions_url: str = ""
    hime_reader_flow_url: str = ""
    hime_reader_emotion_url: str = ""
    hime_reader_yuri_url: str = ""

    # v1.2.1 — Embeddings + RAG
    hime_embeddings_dir: str = ""   # blank → resolved from paths.EMBEDDINGS_DIR at runtime
    hime_rag_dir: str = ""          # blank → resolved from paths.RAG_DIR at runtime
    hime_allow_downloads: bool = False  # gates the model download endpoint

    # Pipeline Stage 4 — Reader Panel + Aggregator (v2)
    stage4_reader_model_id: str = "unsloth/Qwen3.5-2B-bnb-4bit"
    stage4_aggregator_model_id: str = "LiquidAI/LFM2-24B-A2B"
    stage4_reader_dtype: str = "nf4"       # nf4 | fp4 | fp16
    stage4_aggregator_dtype: str = "int4"  # int4 | fp16
    stage4_max_retries: int = 3            # max Stage 3→4 retry cycles before forced okay

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
    )


settings = Settings()
