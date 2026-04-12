# scripts/vault_indexer/config.py
"""Zentrale Konfiguration für den Hime-Vault-Indexer.

Alle Werte via Env-Vars überschreibbar (für CI/Tests).
"""
from __future__ import annotations

import os
from pathlib import Path

# Projekt-Root: 2 Ebenen über scripts/vault_indexer/
ROOT = Path(__file__).resolve().parents[2]

VAULT_PATH      = Path(os.environ.get("HIME_VAULT_PATH",  str(ROOT / "Hime-vault")))
QDRANT_URL      = os.environ.get("QDRANT_URL",            "http://localhost:23612")
COLLECTION      = os.environ.get("HIME_VAULT_COLLECTION", "hime-vault")
OLLAMA_BASE     = os.environ.get("OLLAMA_BASE_URL",        "http://localhost:11434")
EMBED_MODEL     = os.environ.get("EMBED_MODEL",            "bge-m3")
EXCLUDE_DIRS: set[str] = set(
    os.environ.get("EXCLUDE_DIRS", ".trash,.obsidian,.git").split(",")
)
