"""
Lexicon-based literal translation anchor.

Uses MeCab (with unidic-lite, no model download) for tokenization and
jamdict (JMdict) for word-level glosses. The output is intentionally rough
— it serves as a completeness anchor for the consensus merger, not as a
fluent translation.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import BaseModel

_log = logging.getLogger(__name__)


class LexiconToken(BaseModel):
    surface: str
    reading: str | None = None
    pos: str
    base_form: str | None = None
    glosses: list[str] = []


class LexiconResult(BaseModel):
    tokens: list[LexiconToken]
    literal_translation: str
    unknown_tokens: list[str]
    confidence: float


@lru_cache(maxsize=1)
def _get_tagger():
    import MeCab
    return MeCab.Tagger()


@lru_cache(maxsize=1)
def _get_jam():
    from jamdict import Jamdict
    return Jamdict()


def _glosses_for(jam, word: str) -> list[str]:
    try:
        result = jam.lookup(word)
        out: list[str] = []
        for entry in result.entries:
            for sense in entry.senses:
                for g in sense.gloss:
                    out.append(g.text)
                if len(out) >= 4:
                    return out[:4]
        return out[:4]
    except Exception:  # noqa: BLE001
        return []


class LexiconService:
    def translate(self, text: str) -> LexiconResult:
        if not text or not text.strip():
            return LexiconResult(
                tokens=[], literal_translation="", unknown_tokens=[], confidence=0.0,
            )

        tagger = _get_tagger()
        jam = _get_jam()

        tokens: list[LexiconToken] = []
        unknown: list[str] = []
        gloss_pieces: list[str] = []
        known_count = 0
        total_count = 0

        node = tagger.parseToNode(text)
        while node:
            surface = node.surface
            if surface and surface.strip():
                total_count += 1
                features = (node.feature or "").split(",")
                pos = features[0] if features else "*"
                base_form = features[6] if len(features) > 6 and features[6] != "*" else None
                reading = features[7] if len(features) > 7 and features[7] != "*" else None

                glosses = _glosses_for(jam, base_form or surface)
                if glosses:
                    known_count += 1
                    gloss_pieces.append(glosses[0])
                else:
                    unknown.append(surface)

                tokens.append(LexiconToken(
                    surface=surface,
                    reading=reading,
                    pos=pos,
                    base_form=base_form,
                    glosses=glosses,
                ))
            node = node.next

        literal = " ".join(gloss_pieces)
        confidence = (known_count / total_count) if total_count > 0 else 0.0
        return LexiconResult(
            tokens=tokens,
            literal_translation=literal,
            unknown_tokens=unknown,
            confidence=round(confidence, 3),
        )
