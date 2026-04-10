"""
Reader / Critic Panel — 6 persona prompts that review a finished translation.

Each persona runs against a configurable local inference endpoint. If the
endpoint URL is empty, the panel falls back to `HIME_QWEN14B_URL` so the
panel still works in single-model setups.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..config import settings

_log = logging.getLogger(__name__)

Severity = Literal["info", "warning", "error"]


class ReviewFinding(BaseModel):
    reader: str
    severity: Severity
    paragraph_id: int | None = None
    finding: str
    suggestion: str | None = None


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "readers"

_READERS: list[tuple[str, str, str]] = [
    ("name_consistency",     "reader_name_consistency.txt",     "hime_reader_names_url"),
    ("register",             "reader_register.txt",             "hime_reader_register_url"),
    ("omissions",            "reader_omissions.txt",            "hime_reader_omissions_url"),
    ("natural_flow",         "reader_natural_flow.txt",         "hime_reader_flow_url"),
    ("emotional_continuity", "reader_emotional_continuity.txt", "hime_reader_emotion_url"),
    ("yuri_register",        "reader_yuri_register.txt",        "hime_reader_yuri_url"),
]


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _resolve_url(attr: str) -> str:
    url = getattr(settings, attr, "") or ""
    if url:
        return url
    return settings.hime_qwen14b_url  # fallback


class ReaderPanel:
    async def review(
        self, *, translation: str, source: str | None,
    ) -> list[ReviewFinding]:
        if not translation or not translation.strip():
            return []

        async def run_one(reader_id: str, prompt_file: str, url_attr: str) -> list[ReviewFinding]:
            system = _load_prompt(prompt_file)
            if not system:
                return []
            url = _resolve_url(url_attr)
            user = (
                f"Translation:\n{translation}\n\n"
                + (f"Source (Japanese):\n{source}\n\n" if source else "")
                + "Return a JSON array of findings, or [] if none."
            )
            try:
                raw = await self._call_model(
                    url, settings.hime_reader_model,
                    [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
                )
            except Exception as e:  # noqa: BLE001
                _log.warning("[reader %s] inference failed: %s", reader_id, e)
                return []
            return self._parse(raw, reader_id)

        results = await asyncio.gather(
            *[run_one(rid, fn, attr) for rid, fn, attr in _READERS],
            return_exceptions=False,
        )
        flat: list[ReviewFinding] = []
        for findings in results:
            flat.extend(findings)
        return flat

    @staticmethod
    def _parse(raw: str, reader: str) -> list[ReviewFinding]:
        # Be lenient: strip code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if "\n" in text:
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        out: list[ReviewFinding] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                out.append(ReviewFinding(reader=reader, **entry))
            except Exception:  # noqa: BLE001
                continue
        return out

    async def _call_model(
        self, url: str, model: str, messages: list[dict],
    ) -> str:
        """Wrap the existing OpenAI-compatible streaming call into a single full response."""
        from ..inference import stream_completion
        buf: list[str] = []
        async for token in stream_completion(url, model, messages):
            buf.append(token)
        return "".join(buf)
