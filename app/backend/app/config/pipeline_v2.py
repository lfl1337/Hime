"""Centralized model ID + path registry for Pipeline v2.

Single source of truth — Stage 2, Stage 3, and future stages read from here
instead of hardcoding HF IDs in their own modules. Environment variables
override defaults for local path pinning.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..core.paths import MODELS_DIR


# Stage 1A — Qwen2.5-32B + LoRA
STAGE1A_MODEL_ID: str = os.environ.get(
    "HIME_STAGE1A_MODEL_ID",
    "lmstudio-community/Qwen2.5-32B-Instruct-GGUF",
)
STAGE1A_LOCAL_PATH: Path = Path(os.environ.get(
    "HIME_STAGE1A_LOCAL_PATH",
    str(MODELS_DIR / "lmstudio-community" / "Qwen2.5-32B-Instruct-GGUF"),
))

# Stage 1B — TranslateGemma-12B-IT
STAGE1B_MODEL_ID: str = os.environ.get(
    "HIME_STAGE1B_MODEL_ID",
    "google/translategemma-12b-it",
)
STAGE1B_LOCAL_PATH: Path = Path(os.environ.get(
    "HIME_STAGE1B_LOCAL_PATH",
    str(MODELS_DIR / "translategemma-12b"),
))

# Stage 1C — Qwen3-9B
STAGE1C_MODEL_ID: str = os.environ.get(
    "HIME_STAGE1C_MODEL_ID",
    "Qwen/Qwen3-9B",
)
STAGE1C_LOCAL_PATH: Path = Path(os.environ.get(
    "HIME_STAGE1C_LOCAL_PATH",
    str(MODELS_DIR / "qwen3-9b"),
))

# Stage 1D — Gemma4 E4B
STAGE1D_MODEL_ID: str = os.environ.get(
    "HIME_STAGE1D_MODEL_ID",
    "google/gemma-4-e4b",
)
STAGE1D_LOCAL_PATH: Path = Path(os.environ.get(
    "HIME_STAGE1D_LOCAL_PATH",
    str(MODELS_DIR / "gemma4-e4b"),
))

# Stage 2 — TranslateGemma-27B-IT (Merger)
STAGE2_MODEL_ID: str = os.environ.get(
    "HIME_STAGE2_MODEL_ID",
    "google/translategemma-27b-it",
)
STAGE2_LOCAL_PATH: Path = Path(os.environ.get(
    "HIME_STAGE2_LOCAL_PATH",
    str(MODELS_DIR / "translategemma-27b"),
))

# Stage 3 — Qwen3-30B-A3B MoE (Polish)
STAGE3_MODEL_ID: str = os.environ.get(
    "HIME_STAGE3_MODEL_ID",
    "Qwen/Qwen3-30B-A3B",
)
STAGE3_LOCAL_PATH: Path = Path(os.environ.get(
    "HIME_STAGE3_LOCAL_PATH",
    str(MODELS_DIR / "qwen3-30b"),
))

# Stage 4 — Reader Panel (Qwen3-2B × 15 personas)
STAGE4_READER_MODEL_ID: str = os.environ.get(
    "HIME_STAGE4_READER_MODEL_ID",
    str(MODELS_DIR / "qwen3-2b"),
)

# Stage 4 — Aggregator (LFM2-24B)
STAGE4_AGGREGATOR_MODEL_ID: str = os.environ.get(
    "HIME_STAGE4_AGGREGATOR_MODEL_ID",
    str(MODELS_DIR / "lfm2-24b"),
)


def get_all_model_ids() -> dict[str, str]:
    """Return all Pipeline v2 model IDs as a dict for diagnostics."""
    # Stage 4 IDs come from Settings (read from .env) rather than os.environ directly.
    # Import lazily to avoid circular imports at module load time.
    from . import settings as _settings  # noqa: PLC0415
    return {
        "stage1a": STAGE1A_MODEL_ID,
        "stage1b": STAGE1B_MODEL_ID,
        "stage1c": STAGE1C_MODEL_ID,
        "stage1d": STAGE1D_MODEL_ID,
        "stage2": STAGE2_MODEL_ID,
        "stage3": STAGE3_MODEL_ID,
        "stage4_reader": str(getattr(_settings, "stage4_reader_model_id", STAGE4_READER_MODEL_ID)),
        "stage4_aggregator": str(getattr(_settings, "stage4_aggregator_model_id", STAGE4_AGGREGATOR_MODEL_ID)),
    }
