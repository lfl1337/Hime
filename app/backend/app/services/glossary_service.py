"""
Glossary / translation memory service.

Manages per-book glossaries with manual + auto-extracted terms. Provides a
prompt-formatting helper that returns ONLY the entries appearing in the
current source text, so the Stage 1 prompt isn't bloated.
"""
from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Glossary as GlossaryORM
from ..models import GlossaryTerm as GlossaryTermORM


class GlossaryTerm(BaseModel):
    id: int | None = None
    glossary_id: int
    source_term: str
    target_term: str
    category: str | None = None
    notes: str | None = None
    occurrences: int = 0
    is_locked: bool = False


class Glossary(BaseModel):
    id: int
    book_id: int | None
    series_id: int | None


# Heuristic regex for Japanese proper-noun-ish katakana / kanji runs
_KATAKANA_RUN = re.compile(r"[\u30A0-\u30FF]{2,}")
_KANJI_RUN = re.compile(r"[\u4E00-\u9FFF]{2,4}")


class GlossaryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_for_book(self, book_id: int) -> Glossary:
        result = await self.session.execute(
            select(GlossaryORM).where(GlossaryORM.book_id == book_id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return Glossary(id=existing.id, book_id=existing.book_id, series_id=existing.series_id)
        new = GlossaryORM(book_id=book_id, series_id=None)
        self.session.add(new)
        await self.session.commit()
        await self.session.refresh(new)
        return Glossary(id=new.id, book_id=new.book_id, series_id=new.series_id)

    async def list_terms(self, glossary_id: int) -> list[GlossaryTerm]:
        result = await self.session.execute(
            select(GlossaryTermORM).where(GlossaryTermORM.glossary_id == glossary_id)
        )
        return [
            GlossaryTerm(
                id=t.id,
                glossary_id=t.glossary_id,
                source_term=t.source_term,
                target_term=t.target_term,
                category=t.category,
                notes=t.notes,
                occurrences=t.occurrences,
                is_locked=t.is_locked,
            )
            for t in result.scalars().all()
        ]

    async def add_term(
        self,
        glossary_id: int,
        source_term: str,
        target_term: str,
        category: str | None,
        notes: str | None,
        is_locked: bool = False,
    ) -> GlossaryTerm:
        orm = GlossaryTermORM(
            glossary_id=glossary_id,
            source_term=source_term,
            target_term=target_term,
            category=category,
            notes=notes,
            is_locked=is_locked,
        )
        self.session.add(orm)
        await self.session.commit()
        await self.session.refresh(orm)
        return GlossaryTerm(
            id=orm.id, glossary_id=orm.glossary_id, source_term=orm.source_term,
            target_term=orm.target_term, category=orm.category, notes=orm.notes,
            occurrences=orm.occurrences, is_locked=orm.is_locked,
        )

    async def update_term(self, term_id: int, **fields) -> GlossaryTerm | None:
        orm = await self.session.get(GlossaryTermORM, term_id)
        if orm is None:
            return None
        for k, v in fields.items():
            if hasattr(orm, k) and v is not None:
                setattr(orm, k, v)
        await self.session.commit()
        await self.session.refresh(orm)
        return GlossaryTerm(
            id=orm.id, glossary_id=orm.glossary_id, source_term=orm.source_term,
            target_term=orm.target_term, category=orm.category, notes=orm.notes,
            occurrences=orm.occurrences, is_locked=orm.is_locked,
        )

    async def get_term(self, term_id: int) -> GlossaryTerm | None:
        orm = await self.session.get(GlossaryTermORM, term_id)
        if orm is None:
            return None
        return GlossaryTerm(
            id=orm.id, glossary_id=orm.glossary_id, source_term=orm.source_term,
            target_term=orm.target_term, category=orm.category, notes=orm.notes,
            occurrences=orm.occurrences, is_locked=orm.is_locked,
        )

    async def delete_term(self, term_id: int) -> bool:
        orm = await self.session.get(GlossaryTermORM, term_id)
        if orm is None:
            return False
        await self.session.delete(orm)
        await self.session.commit()
        return True

    async def format_for_prompt(self, glossary_id: int, source_text: str) -> str:
        terms = await self.list_terms(glossary_id)
        present = [t for t in terms if t.source_term and t.source_term in source_text]
        if not present:
            return ""
        lines = ["Glossary (use these renderings consistently):"]
        for t in present:
            cat = f" [{t.category}]" if t.category else ""
            lines.append(f"  {t.source_term} → {t.target_term}{cat}")
        return "\n".join(lines)

    async def auto_extract_from_translation(
        self,
        glossary_id: int,
        source_text: str,
        translated_text: str,
    ) -> list[GlossaryTerm]:
        """
        Heuristic extraction of repeated proper-noun-shaped tokens from the source.
        Returns candidates the caller can review; adds them to the glossary with
        placeholder target_term and category="auto".
        """
        candidates: Counter[str] = Counter()
        for m in _KATAKANA_RUN.finditer(source_text):
            candidates[m.group()] += 1
        for m in _KANJI_RUN.finditer(source_text):
            candidates[m.group()] += 1
        suggested: list[GlossaryTerm] = []
        existing = {t.source_term for t in await self.list_terms(glossary_id)}
        for term, count in candidates.most_common(10):
            if term in existing or count < 2:
                continue
            new_term = await self.add_term(
                glossary_id=glossary_id,
                source_term=term,
                target_term=term,  # placeholder — user edits
                category="auto",
                notes=f"Auto-extracted, {count} occurrences. Edit the target.",
            )
            suggested.append(new_term)
        return suggested
