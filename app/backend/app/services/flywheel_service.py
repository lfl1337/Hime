"""
Flywheel service: export reviewed translations as training JSONL.

Reads paragraphs marked is_reviewed=True with verification_result.fidelity_score
above the threshold and appends them to data/training/hime_flywheel.jsonl.
Deduplicates against the existing file by hashing source text.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.paths import TRAINING_DATA_DIR
from ..models import Paragraph

DEFAULT_OUT = TRAINING_DATA_DIR / "hime_flywheel.jsonl"

_INSTRUCTION = "Translate the following Japanese text to English."


class FlywheelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def export_reviewed_to_training_data(
        self,
        *,
        out_path: Path | None = None,
        min_quality: float = 0.8,
    ) -> int:
        out = Path(out_path or DEFAULT_OUT)
        out.parent.mkdir(parents=True, exist_ok=True)

        existing_hashes: set[str] = set()
        if out.exists():
            for line in out.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    existing_hashes.add(_hash(entry.get("input", "")))
                except json.JSONDecodeError:
                    continue

        result = await self.session.execute(
            select(Paragraph).where(Paragraph.is_reviewed == True)  # noqa: E712
        )
        rows = result.scalars().all()

        new_entries: list[dict] = []
        for p in rows:
            if not p.translated_text or not p.source_text:
                continue
            score = _extract_fidelity(p.verification_result)
            if score < min_quality:
                continue
            h = _hash(p.source_text)
            if h in existing_hashes:
                continue
            existing_hashes.add(h)
            new_entries.append({
                "instruction": _INSTRUCTION,
                "input": p.source_text,
                "output": p.translated_text,
                "score": 1.0,
                "source": "hime_flywheel",
            })

        with out.open("a", encoding="utf-8") as f:
            for entry in new_entries:
                f.write(json.dumps(entry, ensure_ascii=False))
                f.write("\n")
        return len(new_entries)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_fidelity(verification_json: str | None) -> float:
    if not verification_json:
        return 0.0
    try:
        data = json.loads(verification_json)
        return float(data.get("fidelity_score", 0.0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0
