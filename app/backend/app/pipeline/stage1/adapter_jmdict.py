"""
Stage 1E — JMdict literal translation via LexiconService.

This adapter is synchronous and always succeeds. It is the completeness anchor
for the consensus merger — providing a word-by-word gloss even when all neural
models fail. Never raises; returns "" on any internal error.
"""
from __future__ import annotations

import logging

from ...services.lexicon_service import LexiconService

_log = logging.getLogger(__name__)


def translate(source_jp: str) -> str:
    """
    Return a space-separated literal English gloss of source_jp via JMdict.

    Always returns a str (may be empty). Never raises.
    """
    try:
        result = LexiconService().translate(source_jp)
        return result.literal_translation
    except Exception as exc:  # noqa: BLE001
        _log.warning("JMdict adapter failed: %s", exc)
        return ""
