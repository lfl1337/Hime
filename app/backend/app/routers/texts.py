from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_api_key
from ..database import get_session
from ..middleware.rate_limit import limiter
from ..models import SourceText
from ..schemas import SourceTextCreate, SourceTextRead
from ..utils.sanitize import sanitize_text

router = APIRouter(prefix="/texts", tags=["texts"])


@router.post("/", response_model=SourceTextRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_text(
    request: Request,
    body: SourceTextCreate,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
) -> SourceText:
    body.title = sanitize_text(body.title, "title")
    body.content = sanitize_text(body.content, "content")

    text = SourceText(**body.model_dump())
    session.add(text)
    await session.commit()
    await session.refresh(text)
    return text


@router.get("/", response_model=list[SourceTextRead])
async def list_texts(
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[SourceText]:
    result = await session.execute(
        select(SourceText)
        .order_by(SourceText.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
    )
    return list(result.scalars().all())


@router.get("/{text_id}", response_model=SourceTextRead)
async def get_text(
    text_id: int,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
) -> SourceText:
    text = await session.get(SourceText, text_id)
    if not text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text not found")
    return text


@router.delete("/{text_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_text(
    text_id: int,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
) -> None:
    text = await session.get(SourceText, text_id)
    if not text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text not found")
    await session.delete(text)
    await session.commit()
