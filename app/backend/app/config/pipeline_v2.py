"""Centralized model ID + path registry for Pipeline v2.

Single source of truth for all stage model IDs and local paths.
Uses Pydantic BaseSettings to correctly read from .env (POST-1 fix:
raw os.environ.get() at import-time was ignoring .env values).
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..core.paths import MODELS_DIR

# --- Locate .env (mirrors config/__init__.py logic) ---
_HIME_DATA_DIR = os.environ.get("HIME_DATA_DIR")
_ENV_FILE = (
    Path(_HIME_DATA_DIR) / ".env"
    if _HIME_DATA_DIR
    else Path(__file__).parent.parent.parent / ".env"
)


class _PipelineV2Settings(BaseSettings):
    """Model ID + local path settings for Pipeline v2.

    Field names match HIME_* env-var names (via alias).
    Values loaded from .env file + shell env (shell takes priority).
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    hime_stage1a_model_id: str = Field(
        default="lmstudio-community/Qwen2.5-32B-Instruct-GGUF"
    )
    hime_stage1a_local_path: str = Field(
        default=str(MODELS_DIR / "lmstudio-community" / "Qwen2.5-32B-Instruct-GGUF")
    )

    hime_stage1b_model_id: str = Field(default="google/translategemma-12b-it")
    hime_stage1b_local_path: str = Field(
        default=str(MODELS_DIR / "translategemma-12b")
    )

    hime_stage1c_model_id: str = Field(default="Qwen/Qwen3.5-9B")
    hime_stage1c_local_path: str = Field(default=str(MODELS_DIR / "qwen3-9b"))

    # Stage 1D: LLM-jp-3-7.2B-Instruct3 (Japanese-native, NF4 4-bit)
    hime_stage1d_model_id: str = Field(default="llm-jp/llm-jp-3-7.2b-instruct3")
    hime_stage1d_local_path: str = Field(default=str(MODELS_DIR / "llm-jp-3-7b"))

    hime_stage2_model_id: str = Field(default="google/translategemma-27b-it")
    hime_stage2_local_path: str = Field(
        default=str(MODELS_DIR / "translategemma-27b")
    )

    hime_stage3_model_id: str = Field(default="Qwen/Qwen3-30B-A3B")
    hime_stage3_local_path: str = Field(default=str(MODELS_DIR / "qwen3-30b"))

    hime_stage4_reader_model_id: str = Field(
        default=str(MODELS_DIR / "qwen3.5-2b")
    )
    hime_stage4_aggregator_model_id: str = Field(
        default=str(MODELS_DIR / "lfm2-24b")
    )


_cfg = _PipelineV2Settings()

# ---------------------------------------------------------------------------
# Public module-level constants — interface UNCHANGED, downstream imports work.
# ---------------------------------------------------------------------------
STAGE1A_MODEL_ID: str = _cfg.hime_stage1a_model_id
STAGE1A_LOCAL_PATH: Path = Path(_cfg.hime_stage1a_local_path)
STAGE1B_MODEL_ID: str = _cfg.hime_stage1b_model_id
STAGE1B_LOCAL_PATH: Path = Path(_cfg.hime_stage1b_local_path)
STAGE1C_MODEL_ID: str = _cfg.hime_stage1c_model_id
STAGE1C_LOCAL_PATH: Path = Path(_cfg.hime_stage1c_local_path)
STAGE1D_MODEL_ID: str = _cfg.hime_stage1d_model_id
STAGE1D_LOCAL_PATH: Path = Path(_cfg.hime_stage1d_local_path)
STAGE2_MODEL_ID: str = _cfg.hime_stage2_model_id
STAGE2_LOCAL_PATH: Path = Path(_cfg.hime_stage2_local_path)
STAGE3_MODEL_ID: str = _cfg.hime_stage3_model_id
STAGE3_LOCAL_PATH: Path = Path(_cfg.hime_stage3_local_path)
STAGE4_READER_MODEL_ID: str = _cfg.hime_stage4_reader_model_id
STAGE4_AGGREGATOR_MODEL_ID: str = _cfg.hime_stage4_aggregator_model_id


def get_all_model_ids() -> dict[str, str]:
    """Return all Pipeline v2 model IDs as a dict (for diagnostics/health checks)."""
    return {
        "stage1a": STAGE1A_MODEL_ID,
        "stage1b": STAGE1B_MODEL_ID,
        "stage1c": STAGE1C_MODEL_ID,
        "stage1d": STAGE1D_MODEL_ID,
        "stage2": STAGE2_MODEL_ID,
        "stage3": STAGE3_MODEL_ID,
        "stage4_reader": STAGE4_READER_MODEL_ID,
        "stage4_aggregator": STAGE4_AGGREGATOR_MODEL_ID,
    }
