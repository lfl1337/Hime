# scripts/shuukura_rag/common.py
"""Shared utilities for all Shuukura RAG pipeline phases."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# --- Pfade ---
ROOT = Path(__file__).resolve().parents[2]          # N:/Projekte/NiN/Hime
sys.path.insert(0, str(ROOT / "app" / "backend"))   # backend-Package importierbar machen

STAGING_DIR = ROOT / "data" / "rag" / "staging" / "shuukura"
STATE_FILE  = STAGING_DIR / "state.json"
RAW_JP_DIR  = ROOT / "data" / "raw_imports" / "shuukura"
EN_EPUB_DIR = ROOT / "data" / "epubs" / "Shuukura"


def load_state() -> dict:
    """Lädt den gemeinsamen Zustand aus state.json."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    """Persistiert den Zustand in state.json (merge mit bestehendem Inhalt)."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_state()
    existing.update(state)
    STATE_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_report_dir() -> Path:
    """Gibt den Report-Ordner aus state.json zurück (muss Phase 0 gesetzt haben)."""
    state = load_state()
    rd = state.get("report_dir")
    if not rd:
        raise RuntimeError("report_dir fehlt in state.json — Phase 0 zuerst ausführen.")
    return Path(rd)


def write_report(filename: str, content: str) -> None:
    """Schreibt eine Markdown-Reportdatei in den Report-Ordner."""
    rd = get_report_dir()
    rd.mkdir(parents=True, exist_ok=True)
    (rd / filename).write_text(content, encoding="utf-8")
    print(f"[report] {rd / filename}")


def halt(reason: str) -> None:
    """Stoppt die Pipeline mit einer klaren Fehlermeldung."""
    print(f"\n{'='*60}")
    print(f"HALT: {reason}")
    print(f"{'='*60}\n")
    sys.exit(1)
