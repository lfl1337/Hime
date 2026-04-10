"""
Bilingual fidelity verification using Qwen2.5-32B.

Loads `app/backend/app/prompts/verify_bilingual.txt` (already present from
v1.2.0), substitutes the JP source and EN translation, sends to the local
inference endpoint, and parses the structured response.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..config import settings

_log = logging.getLogger(__name__)


class VerificationResult(BaseModel):
    fidelity_score: float
    missing_content: list[str]
    added_content: list[str]
    register_match: Literal["match", "drift", "wrong"]
    name_check: Literal["consistent", "inconsistent"]
    overall: Literal["pass", "warning", "fail"]


_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "verify_bilingual.txt"


def _load_template() -> str:
    if _TEMPLATE_PATH.exists():
        return _TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        "Compare the Japanese source text and the English translation. "
        "Return a JSON object with fields: fidelity_score (0-1), "
        "missing_content (list), added_content (list), register_match "
        "(match|drift|wrong), name_check (consistent|inconsistent), overall (pass|warning|fail).\n\n"
        "Japanese:\n{jp}\n\nEnglish:\n{en}"
    )


_JSON_BLOCK = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _extract_json(raw: str) -> dict | None:
    text = raw.strip()
    # Strip code fences
    if text.startswith("```"):
        inner = re.sub(r"^```(?:json)?\s*", "", text)
        inner = re.sub(r"```\s*$", "", inner)
        text = inner.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: find the first balanced-looking object
    matches = _JSON_BLOCK.findall(raw)
    for m in matches:
        try:
            return json.loads(m)
        except json.JSONDecodeError:
            continue
    return None


class VerificationService:
    async def verify_paragraph(self, *, jp: str, en: str) -> VerificationResult:
        template = _load_template()
        prompt = template.replace("{jp}", jp).replace("{en}", en)
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = await self._call_model(
                settings.hime_qwen32b_url,
                settings.hime_qwen32b_model,
                messages,
                temperature=0.2,
            )
        except Exception as e:  # noqa: BLE001
            _log.warning("verification call failed: %s", e)
            return self._warning_default()

        data = _extract_json(raw)
        if not data:
            return self._warning_default()
        try:
            return VerificationResult.model_validate(data)
        except Exception:  # noqa: BLE001
            return self._warning_default()

    @staticmethod
    def _warning_default() -> VerificationResult:
        return VerificationResult(
            fidelity_score=0.0,
            missing_content=[],
            added_content=[],
            register_match="match",
            name_check="consistent",
            overall="warning",
        )

    async def _call_model(
        self, url: str, model: str, messages: list[dict], temperature: float = 0.2,
    ) -> str:
        from ..inference import stream_completion
        buf: list[str] = []
        async for token in stream_completion(url, model, messages):
            buf.append(token)
        return "".join(buf)
