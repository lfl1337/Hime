"""Read-only data registry endpoints.

The registry is managed via the CLI (scripts/hime_data.py). This router
exposes it to the frontend for display/dashboard use.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.paths import DATA_DIR, PROJECT_ROOT, validate_within_directory

router = APIRouter(prefix="/data/registry", tags=["data-registry"])


class RegistryEntry(BaseModel):
    id: str
    path: str
    kind: str
    source: str
    lines: int
    quality_field: str = ""
    quality_range: list[float] = []
    added: str
    notes: str = ""


class RegistryEntryDetail(RegistryEntry):
    samples: list[dict]


def _registry_path() -> Path:
    return DATA_DIR / "registry.jsonl"


def _load_entries() -> list[dict]:
    path = _registry_path()
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


@router.get("", response_model=list[RegistryEntry])
async def list_registry() -> list[RegistryEntry]:
    """Return all registered training data sources."""
    return [RegistryEntry(**e) for e in _load_entries()]


@router.get("/{entry_id}", response_model=RegistryEntryDetail)
async def get_registry_entry(entry_id: str) -> RegistryEntryDetail:
    """Return one entry plus up to 3 sample rows."""
    for entry in _load_entries():
        if entry["id"] == entry_id:
            src = PROJECT_ROOT / entry["path"]
            try:
                validate_within_directory(src, PROJECT_ROOT)
            except ValueError:
                raise HTTPException(status_code=422, detail="registry path escapes project root")
            samples: list[dict] = []
            if src.exists():
                with src.open("r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i >= 3:
                            break
                        try:
                            samples.append(json.loads(line))
                        except Exception:
                            pass
            return RegistryEntryDetail(**entry, samples=samples)
    raise HTTPException(status_code=404, detail=f"registry entry not found: {entry_id}")
