"""
postprocessor.py — Reassemble translated paragraph segments into chapter text.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Book, Chapter, Paragraph


def reassemble_chapter(paragraphs: list[tuple[int, str]], chapter_title: str) -> str:
    """
    Join translated paragraphs back into chapter text with title.
    Returns full chapter text: title line, blank line, paragraphs separated by double newlines.
    """
    lines: list[str] = [chapter_title, ""]
    for _idx, text in paragraphs:
        lines.append(text.strip())
    return "\n\n".join(lines)


async def postprocess_book(book_id: int, session: AsyncSession) -> dict[int, str]:
    """
    Return {chapter_id: full_translated_text} for all chapters of a book.
    Falls back to [untranslated: ...] for untranslated paragraphs.
    """
    result = await session.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.chapter_index)
    )
    chapters = result.scalars().all()

    chapter_texts: dict[int, str] = {}
    for chapter in chapters:
        para_result = await session.execute(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
        paragraphs = para_result.scalars().all()

        para_tuples: list[tuple[int, str]] = []
        for p in paragraphs:
            if p.translated_text:
                para_tuples.append((p.paragraph_index, p.translated_text))
            else:
                fallback = f"[untranslated: {p.source_text[:80]}]"
                para_tuples.append((p.paragraph_index, fallback))

        chapter_texts[chapter.id] = reassemble_chapter(para_tuples, chapter.title)

    return chapter_texts
