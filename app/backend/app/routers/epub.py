"""EPUB library endpoints."""
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..middleware.rate_limit import limiter
from ..utils.sanitize import sanitize_text
from ..services.epub_service import (
    export_chapter,
    get_chapters,
    get_library,
    get_paragraphs,
    get_setting,
    import_epub,
    rescan_book_chapters,
    save_translation,
    set_setting,
    update_book_series,
)

router = APIRouter(prefix="/epub", tags=["epub"])


class ImportRequest(BaseModel):
    file_path: str


class TranslationRequest(BaseModel):
    text: str = Field(..., max_length=50_000)


class SettingRequest(BaseModel):
    key: str = Field(..., pattern=r"^(epub_watch_folder|auto_scan_interval)$")
    value: str = Field(..., max_length=1024)


class BookUpdateRequest(BaseModel):
    series_id: int | None = None
    series_title: str | None = Field(default=None, max_length=512)


class ExportFormat(str, Enum):
    txt = "txt"


@router.post("/import", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def api_import_epub(
    request: Request,
    body: ImportRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Reject null bytes and env var syntax in file path
    if "\x00" in body.file_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")
    if "${" in body.file_path or "%" in body.file_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")

    file_path = Path(body.file_path).resolve()
    if file_path.suffix.lower() != ".epub":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .epub files allowed")

    # Path traversal: must be inside the watch folder
    watch_folder_str = await get_setting("epub_watch_folder", session)
    if watch_folder_str:
        watch_folder = Path(watch_folder_str).resolve()
        if not file_path.is_relative_to(watch_folder):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Path outside allowed folder")

    # Reject symlinks
    if file_path.is_symlink():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Symbolic links not allowed")

    try:
        return await import_epub(str(file_path), session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.get("/books")
async def api_get_library(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_library(session)


@router.get("/books/{book_id}/chapters")
async def api_get_chapters(
    book_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_chapters(book_id, session)


@router.get("/chapters/{chapter_id}/paragraphs")
async def api_get_paragraphs(
    chapter_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_paragraphs(chapter_id, session)


@router.post("/paragraphs/{paragraph_id}/translation", status_code=status.HTTP_204_NO_CONTENT)
async def api_save_translation(
    paragraph_id: int,
    body: TranslationRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    await save_translation(paragraph_id, body.text, session)


@router.get("/export/{chapter_id}")
async def api_export_chapter(
    chapter_id: int,
    format: ExportFormat = Query(default=ExportFormat.txt),  # noqa: A002
    session: AsyncSession = Depends(get_session),
) -> dict:
    text = await export_chapter(chapter_id, format, session)
    return {"content": text}


@router.post("/books/{book_id}/rescan", status_code=status.HTTP_200_OK)
async def api_rescan_book(
    book_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        return await rescan_book_chapters(book_id, session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.patch("/books/{book_id}", status_code=status.HTTP_200_OK)
async def api_update_book(
    book_id: int,
    body: BookUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await update_book_series(
        book_id=book_id,
        series_id=body.series_id,
        series_title=sanitize_text(body.series_title) if body.series_title else None,
        session=session,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return result


@router.get("/settings")
async def api_get_settings(
    session: AsyncSession = Depends(get_session),
) -> dict:
    folder = await get_setting("epub_watch_folder", session)
    interval = await get_setting("auto_scan_interval", session)
    return {
        "epub_watch_folder": folder or "",
        "auto_scan_interval": interval or "60",
    }


@router.post("/settings", status_code=status.HTTP_204_NO_CONTENT)
async def api_update_setting(
    body: SettingRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    await set_setting(body.key, body.value, session)
