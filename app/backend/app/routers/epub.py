"""EPUB library endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..services.epub_service import (
    export_chapter,
    get_chapters,
    get_library,
    get_paragraphs,
    get_setting,
    import_epub,
    save_translation,
    set_setting,
)

router = APIRouter(prefix="/epub", tags=["epub"])


class ImportRequest(BaseModel):
    file_path: str


class TranslationRequest(BaseModel):
    text: str


class SettingRequest(BaseModel):
    key: str
    value: str


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def api_import_epub(
    body: ImportRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        return await import_epub(body.file_path, session)
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
    format: str = Query(default="txt"),  # noqa: A002
    session: AsyncSession = Depends(get_session),
) -> dict:
    text = await export_chapter(chapter_id, format, session)
    return {"content": text}


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
