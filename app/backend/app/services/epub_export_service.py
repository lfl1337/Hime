"""
epub_export_service.py — Build a translated EPUB from translated paragraphs in DB.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.paths import DATA_DIR
from ..models import Book, Chapter, Paragraph
from ..pipeline.postprocessor import postprocess_book

_log = logging.getLogger(__name__)

EXPORTS_DIR = DATA_DIR / "exports"


def _build_epub_sync(
    book_title: str,
    book_author: str | None,
    cover_blob: bytes | None,
    chapter_data: list[dict],  # [{"title": str, "text": str}]
    output_path: Path,
) -> None:
    """Synchronous ebooklib EPUB construction — run inside asyncio.to_thread."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(f"hime-export-{output_path.stem}")
    book.set_title(book_title)
    book.set_language("en")
    if book_author:
        book.add_author(book_author)

    if cover_blob:
        cover_item = epub.EpubItem(
            uid="cover-image",
            file_name="images/cover.jpg",
            media_type="image/jpeg",
            content=cover_blob,
        )
        book.add_item(cover_item)
        book.set_cover("images/cover.jpg", cover_blob)

    chapters: list[epub.EpubHtml] = []
    toc: list[epub.Link] = []
    spine: list[str | epub.EpubHtml] = ["nav"]

    for idx, ch in enumerate(chapter_data):
        ch_id = f"chapter_{idx:04d}"
        ch_filename = f"{ch_id}.xhtml"
        title_safe = ch["title"].replace('"', "&quot;").replace("<", "&lt;")
        paragraphs_html = "".join(
            f"<p>{para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</p>"
            for para in ch["text"].split("\n\n")
            if para.strip() and para.strip() != ch["title"]
        )
        html_content = (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<!DOCTYPE html>'
            f'<html xmlns="http://www.w3.org/1999/xhtml">'
            f'<head><title>{title_safe}</title>'
            f'<link rel="stylesheet" type="text/css" href="../styles/main.css"/>'
            f"</head><body>"
            f"<h1>{title_safe}</h1>"
            f"{paragraphs_html}"
            f"</body></html>"
        )

        ch_item = epub.EpubHtml(
            uid=ch_id,
            file_name=f"Text/{ch_filename}",
            title=ch["title"],
            lang="en",
        )
        ch_item.set_content(html_content.encode("utf-8"))
        book.add_item(ch_item)
        chapters.append(ch_item)
        toc.append(epub.Link(f"Text/{ch_filename}", ch["title"], ch_id))
        spine.append(ch_item)

    css_item = epub.EpubItem(
        uid="style-main",
        file_name="styles/main.css",
        media_type="text/css",
        content=b"body { font-family: serif; line-height: 1.6; margin: 1em 2em; }"
                b" h1 { margin-bottom: 1em; } p { margin: 0.5em 0; text-indent: 1.5em; }",
    )
    book.add_item(css_item)

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book)
    _log.info("[epub-export] Written: %s", output_path)


async def export_book(book_id: int, session: AsyncSession) -> Path:
    """Build an EPUB from translated paragraphs in DB. Returns the output path."""
    book = await session.get(Book, book_id)
    if book is None:
        raise ValueError(f"Book {book_id} not found")

    result = await session.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.chapter_index)
    )
    chapters = result.scalars().all()

    chapter_texts = await postprocess_book(book_id, session)

    chapter_data: list[dict] = [
        {"title": ch.title, "text": chapter_texts.get(ch.id, "")}
        for ch in chapters
    ]

    output_path = EXPORTS_DIR / f"{book_id}_translated.epub"

    await asyncio.to_thread(
        _build_epub_sync,
        book.title,
        book.author,
        book.cover_image_blob,
        chapter_data,
        output_path,
    )

    return output_path
