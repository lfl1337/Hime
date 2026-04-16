"""Shared .env file resolution — single source of truth.

Both config/__init__.py and config/pipeline_v2.py need the .env path.
This module prevents the logic from being duplicated.
"""
import os
from pathlib import Path

_HIME_DATA_DIR = os.environ.get("HIME_DATA_DIR")

ENV_FILE: Path = (
    Path(_HIME_DATA_DIR) / ".env"
    if _HIME_DATA_DIR
    else Path(__file__).parent.parent.parent / ".env"  # dev: app/backend/.env
)
