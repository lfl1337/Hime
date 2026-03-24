"""EPUB parsing, import, and library management service."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import warnings
from datetime import UTC, datetime

from bs4 import XMLParsedAsHTMLWarning
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Book, Chapter, Paragraph, Setting

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str, max_len: int = 400) -> list[str]:
    """Split long text at Japanese sentence boundaries into ≤max_len chunks."""
    parts: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in "。！？" and len(current) >= max_len:
            parts.append(current.strip())
            current = ""
    if current.strip():
        parts.append(current.strip())
    return parts or [text]


def _extract_toc_titles(book) -> dict[str, str]:
    """Return {filename_base: title} from EPUB ToC (NCX or nav)."""
    result: dict[str, str] = {}

    def _recurse(items) -> None:
        for item in items:
            if isinstance(item, tuple):
                link, children = item
                if hasattr(link, 'href') and hasattr(link, 'title') and link.title:
                    base = link.href.split('#')[0].split('/')[-1]
                    result[base] = link.title.strip()
                _recurse(children)
            elif hasattr(item, 'href') and hasattr(item, 'title') and item.title:
                base = item.href.split('#')[0].split('/')[-1]
                result[base] = item.title.strip()

    _recurse(book.toc)
    return result


_ONLY_NUM_PUNCT = re.compile(r'^[\d\s\u3000\-_:.,;!?。、「」『』【】\[\]()（）]+$')


def _is_valid_title(title: str, book_title: str) -> bool:
    """Return False if title is empty, too short, only numbers/punct, or equals book title."""
    t = title.strip().replace('\u3000', ' ')
    if len(t) < 2:
        return False
    if _ONLY_NUM_PUNCT.match(t):
        return False
    if t == book_title.strip():
        return False
    return True


def _split_by_headings(soup, book_title: str, spine_idx: int) -> list[dict]:
    """Split a single large document into sub-chapters at h1/h2 boundaries."""
    sub_chapters: list[dict] = []
    current_title: str | None = None
    current_paragraphs: list[str] = []

    def flush() -> None:
        if current_paragraphs:
            sub_chapters.append({
                "title": current_title or f"Chapter {spine_idx + 1}.{len(sub_chapters) + 1}",
                "paragraphs": current_paragraphs[:],
                "is_front_matter": len(current_paragraphs) < 3,
            })

    body = soup.select_one("body") or soup
    for elem in body.children:
        if not hasattr(elem, 'name') or elem.name is None:
            continue
        local = elem.name.split('}')[-1] if '}' in elem.name else elem.name
        if local in ('h1', 'h2', 'h3'):
            flush()
            current_title = elem.get_text(strip=True).replace('\u3000', ' ') or None
            current_paragraphs = []
        elif local == 'p':
            text = elem.get_text(separator="\n").strip()
            if len(text) >= 10:
                if len(text) > 500:
                    current_paragraphs.extend(_split_sentences(text))
                else:
                    current_paragraphs.append(text)
    flush()
    return sub_chapters


def _parse_epub_sync(file_path: str) -> dict:
    """Synchronous EPUB parsing — run inside asyncio.to_thread."""
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(file_path)

    # Metadata
    title_meta = book.get_metadata("DC", "title")
    title = title_meta[0][0] if title_meta else os.path.basename(file_path)
    author_meta = book.get_metadata("DC", "creator")
    author = author_meta[0][0] if author_meta else None

    # Cover image
    cover_blob: bytes | None = None
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_COVER:
            cover_blob = item.get_content()
            break
    if cover_blob is None:
        for item in book.get_items():
            name = item.get_name().lower()
            if "cover" in name and item.get_type() == ebooklib.ITEM_IMAGE:
                cover_blob = item.get_content()
                break

    # Build ToC title map once
    toc_titles = _extract_toc_titles(book)

    # Chapters — spine order
    chapters: list[dict] = []
    spine_ids = [item_id for item_id, _ in book.spine]
    for idx, item_id in enumerate(spine_ids):
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        html = item.get_content().decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml-xml")

        # Chapter title priority:
        # 1. ToC (pre-built mapping)
        item_filename = item.get_name().split('/')[-1]
        chapter_title = toc_titles.get(item_filename)

        # 2. HTML <title> tag
        if not chapter_title or not _is_valid_title(chapter_title, title):
            title_tag = soup.select_one("title")
            if title_tag:
                candidate = title_tag.get_text(strip=True).replace('\u3000', ' ')
                if _is_valid_title(candidate, title):
                    chapter_title = candidate

        # 3. First heading tag (h1 > h2 > h3)
        if not chapter_title or not _is_valid_title(chapter_title, title):
            heading = soup.select_one("h1, h2, h3")
            if heading:
                candidate = heading.get_text(strip=True).replace('\u3000', ' ')
                if _is_valid_title(candidate, title):
                    chapter_title = candidate

        # 4. Fallback
        if not chapter_title or not _is_valid_title(chapter_title, title):
            chapter_title = f"Chapter {idx + 1}"

        # Paragraphs: collect per <p> tag, then filter/chunk
        raw_paragraphs: list[str] = []
        for p_tag in soup.select("p"):
            text = p_tag.get_text(separator="\n").strip()
            if len(text) >= 10:
                raw_paragraphs.append(text)

        # Fallback: split on double <br> if no <p> tags found
        if not raw_paragraphs:
            raw_html = item.get_content().decode("utf-8", errors="replace")
            chunks = re.split(r'<br\s*/?\s*>\s*(?:\n\s*)?<br\s*/?\s*>', raw_html, flags=re.IGNORECASE)
            for chunk in chunks:
                text = re.sub(r'<[^>]+>', '', chunk).strip()
                if len(text) >= 10:
                    raw_paragraphs.append(text)

        # Final fallback: split on double newlines
        if not raw_paragraphs:
            plain = soup.get_text(separator="\n")
            raw_paragraphs = [p.strip() for p in plain.split("\n\n") if len(p.strip()) >= 10]

        # Chunk paragraphs longer than 500 chars at sentence boundaries
        paragraphs: list[str] = []
        for raw in raw_paragraphs:
            if len(raw) > 500:
                paragraphs.extend(_split_sentences(raw))
            else:
                paragraphs.append(raw)

        # If one spine item contains an entire novel (>200 paragraphs), split by headings
        if len(paragraphs) > 200:
            sub_chapters = _split_by_headings(soup, title, idx)
            if len(sub_chapters) > 1:
                chapters.extend(sub_chapters)
                continue
            _log.warning("[epub] Spine item %s has %d paragraphs — consider re-splitting", item_filename, len(paragraphs))

        if paragraphs:
            chapters.append({
                "title": chapter_title,
                "paragraphs": paragraphs,
                "is_front_matter": len(paragraphs) < 3,
            })

    return {
        "title": title,
        "author": author,
        "cover_blob": cover_blob,
        "chapters": chapters,
    }


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def import_epub(file_path: str, session: AsyncSession) -> dict:
    """Parse an EPUB file and persist it to the database. Returns book summary."""
    # Check if already imported
    result = await session.execute(select(Book).where(Book.file_path == file_path))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return _book_to_dict(existing)

    parsed = await asyncio.to_thread(_parse_epub_sync, file_path)

    book = Book(
        title=parsed["title"],
        author=parsed["author"],
        file_path=file_path,
        cover_image_blob=parsed["cover_blob"],
        total_chapters=len(parsed["chapters"]),
        total_paragraphs=sum(len(c["paragraphs"]) for c in parsed["chapters"]),
    )
    session.add(book)
    await session.flush()  # get book.id

    for ch_idx, ch_data in enumerate(parsed["chapters"]):
        chapter = Chapter(
            book_id=book.id,
            chapter_index=ch_idx,
            title=ch_data["title"],
            total_paragraphs=len(ch_data["paragraphs"]),
            is_front_matter=ch_data["is_front_matter"],
        )
        session.add(chapter)
        await session.flush()  # get chapter.id

        for p_idx, p_text in enumerate(ch_data["paragraphs"]):
            session.add(Paragraph(
                chapter_id=chapter.id,
                paragraph_index=p_idx,
                source_text=p_text,
            ))

    await session.commit()
    await session.refresh(book)
    return _book_to_dict(book)


async def rescan_book_chapters(book_id: int, session: AsyncSession) -> dict:
    """Delete all chapters/paragraphs for a book and re-parse the EPUB."""
    book = await session.get(Book, book_id)
    if book is None:
        raise ValueError(f"Book {book_id} not found")

    result = await session.execute(select(Chapter).where(Chapter.book_id == book_id))
    for ch in result.scalars().all():
        await session.delete(ch)
    await session.flush()

    parsed = await asyncio.to_thread(_parse_epub_sync, book.file_path)
    book.total_chapters = len(parsed["chapters"])
    book.total_paragraphs = sum(len(c["paragraphs"]) for c in parsed["chapters"])
    book.translated_paragraphs = 0
    book.status = "not_started"

    for ch_idx, ch_data in enumerate(parsed["chapters"]):
        chapter = Chapter(
            book_id=book.id,
            chapter_index=ch_idx,
            title=ch_data["title"],
            total_paragraphs=len(ch_data["paragraphs"]),
            is_front_matter=ch_data["is_front_matter"],
        )
        session.add(chapter)
        await session.flush()
        for p_idx, p_text in enumerate(ch_data["paragraphs"]):
            session.add(Paragraph(
                chapter_id=chapter.id,
                paragraph_index=p_idx,
                source_text=p_text,
            ))

    await session.commit()
    await session.refresh(book)
    return _book_to_dict(book)


async def scan_watch_folder(folder_path: str, session: AsyncSession) -> list[str]:
    """Scan folder for EPUB files and import any not yet in the DB."""
    imported: list[str] = []
    if not os.path.isdir(folder_path):
        return imported
    for fname in os.listdir(folder_path):
        if not fname.lower().endswith(".epub"):
            continue
        full_path = os.path.join(folder_path, fname)
        try:
            await import_epub(full_path, session)
            imported.append(full_path)
        except Exception as e:
            _log.warning("[epub] Failed to auto-import %s: %s", full_path, e)
    return imported


async def get_library(session: AsyncSession) -> list[dict]:
    result = await session.execute(select(Book).order_by(Book.imported_at.desc()))
    return [_book_to_dict(b) for b in result.scalars().all()]


async def get_chapters(book_id: int, session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index)
    )
    return [_chapter_to_dict(c) for c in result.scalars().all()]


async def get_paragraphs(chapter_id: int, session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Paragraph).where(Paragraph.chapter_id == chapter_id).order_by(Paragraph.paragraph_index)
    )
    return [_paragraph_to_dict(p) for p in result.scalars().all()]


async def save_translation(paragraph_id: int, text: str, session: AsyncSession) -> None:
    paragraph = await session.get(Paragraph, paragraph_id)
    if paragraph is None:
        return
    paragraph.translated_text = text
    paragraph.is_translated = True
    paragraph.translated_at = datetime.now(UTC)
    await session.flush()

    # Update chapter + book counters
    chapter = await session.get(Chapter, paragraph.chapter_id)
    if chapter:
        result = await session.execute(
            select(Paragraph).where(Paragraph.chapter_id == chapter.id, Paragraph.is_translated == True)  # noqa: E712
        )
        chapter.translated_paragraphs = len(result.scalars().all())
        chapter.status = "complete" if chapter.translated_paragraphs >= chapter.total_paragraphs else "in_progress"
        await session.flush()

        book = await session.get(Book, chapter.book_id)
        if book:
            result2 = await session.execute(
                select(Paragraph)
                .join(Chapter, Paragraph.chapter_id == Chapter.id)
                .where(Chapter.book_id == book.id, Paragraph.is_translated == True)  # noqa: E712
            )
            book.translated_paragraphs = len(result2.scalars().all())
            book.status = "complete" if book.translated_paragraphs >= book.total_paragraphs else "in_progress"

    await session.commit()


async def export_chapter(chapter_id: int, fmt: str, session: AsyncSession) -> str:
    """Export translated chapter as plain text."""
    result = await session.execute(
        select(Paragraph).where(Paragraph.chapter_id == chapter_id).order_by(Paragraph.paragraph_index)
    )
    paragraphs = result.scalars().all()
    lines = [p.translated_text or f"[untranslated: {p.source_text[:80]}]" for p in paragraphs]
    return "\n\n".join(lines)


async def get_setting(key: str, session: AsyncSession) -> str | None:
    setting = await session.get(Setting, key)
    return setting.value if setting else None


async def set_setting(key: str, value: str, session: AsyncSession) -> None:
    setting = await session.get(Setting, key)
    if setting is None:
        session.add(Setting(key=key, value=value))
    else:
        setting.value = value
    await session.commit()


# ---------------------------------------------------------------------------
# Dict helpers
# ---------------------------------------------------------------------------

def _book_to_dict(book: Book) -> dict:
    cover_b64 = None
    if book.cover_image_blob:
        import base64
        cover_b64 = base64.b64encode(book.cover_image_blob).decode()
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "file_path": book.file_path,
        "cover_image_b64": cover_b64,
        "imported_at": book.imported_at.isoformat() if book.imported_at else None,
        "last_accessed": book.last_accessed.isoformat() if book.last_accessed else None,
        "total_chapters": book.total_chapters,
        "total_paragraphs": book.total_paragraphs,
        "translated_paragraphs": book.translated_paragraphs,
        "status": book.status,
    }


def _chapter_to_dict(chapter: Chapter) -> dict:
    return {
        "id": chapter.id,
        "book_id": chapter.book_id,
        "chapter_index": chapter.chapter_index,
        "title": chapter.title,
        "total_paragraphs": chapter.total_paragraphs,
        "translated_paragraphs": chapter.translated_paragraphs,
        "status": chapter.status,
        "is_front_matter": chapter.is_front_matter,
    }


def _paragraph_to_dict(paragraph: Paragraph) -> dict:
    return {
        "id": paragraph.id,
        "chapter_id": paragraph.chapter_id,
        "paragraph_index": paragraph.paragraph_index,
        "source_text": paragraph.source_text,
        "translated_text": paragraph.translated_text,
        "is_translated": paragraph.is_translated,
        "is_skipped": paragraph.is_skipped,
        "translated_at": paragraph.translated_at.isoformat() if paragraph.translated_at else None,
    }
