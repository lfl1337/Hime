from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..middleware.rate_limit import limiter
from ..models import SourceText, Translation
from ..schemas import TranslateJobResponse, TranslateRequest, TranslationRead
from ..utils.sanitize import sanitize_text

router = APIRouter(prefix="/translations", tags=["translations"])


@router.post(
    "/translate",
    response_model=TranslateJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("10/minute")
async def translate_endpoint(
    request: Request,
    body: TranslateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Create a pending pipeline translation job and return its ID.

    Connect to ``ws://127.0.0.1:8000/ws/translate/{job_id}``
    to receive live token streaming for all pipeline stages.
    """
    if body.notes:
        body.notes = sanitize_text(body.notes, "notes")

    source = await session.get(SourceText, body.source_text_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SourceText {body.source_text_id} not found",
        )

    translation = Translation(
        source_text_id=source.id,
        content="",               # populated by pipeline when complete
        model="pipeline",
        notes=body.notes,
        current_stage="pending",
    )
    session.add(translation)
    await session.commit()
    await session.refresh(translation)
    return {"job_id": translation.id}


@router.get("/", response_model=list[TranslationRead])
async def list_translations(
    source_text_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[Translation]:
    q = (
        select(Translation)
        .order_by(Translation.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
    )
    if source_text_id is not None:
        q = q.where(Translation.source_text_id == source_text_id)
    result = await session.execute(q)
    return list(result.scalars().all())


@router.get("/{translation_id}", response_model=TranslationRead)
async def get_translation(
    translation_id: int,
    session: AsyncSession = Depends(get_session),
) -> Translation:
    translation = await session.get(Translation, translation_id)
    if not translation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Translation not found"
        )
    return translation


@router.delete("/{translation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_translation(
    translation_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    # W5: Backend-only/CLI — no frontend caller as of v1.1.2
    translation = await session.get(Translation, translation_id)
    if not translation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Translation not found"
        )
    await session.delete(translation)
    await session.commit()
