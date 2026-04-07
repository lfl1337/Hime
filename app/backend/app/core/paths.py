"""
Centralized path resolution for the Hime backend.

All paths are derived from environment variables with sensible defaults
relative to the project root. This module is the SINGLE SOURCE OF TRUTH
for filesystem paths — import from here instead of hardcoding.

Environment variables (set in .env or system environment):
  HIME_PROJECT_ROOT     — base directory (default: 4 levels up from this file)
  HIME_DATA_DIR         — data directory (default: PROJECT_ROOT/data)
  HIME_MODELS_DIR       — models directory (default: PROJECT_ROOT/modelle)
  HIME_LOGS_DIR         — log directory (default: PROJECT_ROOT/app/backend/logs)
  HIME_EPUB_WATCH_DIR   — EPUB watch directory (default: DATA_DIR/epubs)
  HIME_TRAINING_DATA_DIR — training data (default: DATA_DIR/training)
  HIME_SCRIPTS_DIR      — scripts directory (default: PROJECT_ROOT/scripts)
"""
import os
from pathlib import Path

# PROJECT_ROOT: 4 levels up from app/backend/app/core/paths.py
_DEFAULT_ROOT = Path(__file__).resolve().parents[4]

PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT", str(_DEFAULT_ROOT)))
DATA_DIR = Path(os.environ.get("HIME_DATA_DIR", str(PROJECT_ROOT / "data")))
MODELS_DIR = Path(os.environ.get("HIME_MODELS_DIR", str(PROJECT_ROOT / "modelle")))
LOGS_DIR = Path(os.environ.get("HIME_LOGS_DIR", str(PROJECT_ROOT / "app" / "backend" / "logs")))
EPUB_WATCH_DIR = Path(os.environ.get("HIME_EPUB_WATCH_DIR", str(DATA_DIR / "epubs")))
TRAINING_DATA_DIR = Path(os.environ.get("HIME_TRAINING_DATA_DIR", str(DATA_DIR / "training")))
SCRIPTS_DIR = Path(os.environ.get("HIME_SCRIPTS_DIR", str(PROJECT_ROOT / "scripts")))
TRAINING_LOG_DIR = LOGS_DIR / "training"


def checkpoints_dir(model_name: str) -> Path:
    """Return the checkpoint directory for a specific LoRA model."""
    return Path(os.environ.get(
        "HIME_CHECKPOINTS_DIR",
        str(MODELS_DIR / "lora" / model_name / "checkpoint"),
    ))


def lora_dir(model_name: str) -> Path:
    """Return the LoRA adapter directory for a specific model."""
    return MODELS_DIR / "lora" / model_name
