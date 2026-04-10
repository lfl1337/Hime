"""POST /api/v1/verify — bilingual fidelity verification with paragraph-level caching."""
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Paragraph
from ..services.verification_service import VerificationResult, VerificationService

router = APIRouter(prefix="/verify", tags=["verify"])

_service = VerificationService()


class VerifyRequest(BaseModel):
    jp: str = Field(..., max_length=50_000)
    en: str = Field(..., max_length=50_000)
    paragraph_id: int | None = None
    force: bool = False  # if true, bypasses cached result


@router.post("", response_model=VerificationResult)
async def verify(
    body: VerifyRequest,
    session: AsyncSession = Depends(get_session),
) -> VerificationResult:
    # Cache hit?
    if body.paragraph_id and not body.force:
        result = await session.execute(
            select(Paragraph.verification_result).where(Paragraph.id == body.paragraph_id)
        )
        cached_raw = result.scalar_one_or_none()
        if cached_raw:
            try:
                return VerificationResult.model_validate_json(cached_raw)
            except Exception:
                pass

    fresh = await _service.verify_paragraph(jp=body.jp, en=body.en)

    # Persist
    if body.paragraph_id:
        para = await session.get(Paragraph, body.paragraph_id)
        if para is not None:
            para.verification_result = fresh.model_dump_json()
            await session.commit()

    return fresh
