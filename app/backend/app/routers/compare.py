"""Compare endpoint — thin wrapper that creates a pipeline job from raw text."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import SourceText, Translation
from ..utils.sanitize import sanitize_text

router = APIRouter(prefix="/compare", tags=["compare"])


class CompareRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000)
    notes: str | None = Field(default=None, max_length=2_000)


@router.post("")
async def start_compare(
    body: CompareRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Create a pipeline job from raw text (no pre-existing SourceText needed).
    Returns {"job_id": int}.
    Connect to /ws/translate/{job_id} for live streaming.
    """
    text = sanitize_text(body.text, "text")
    notes = sanitize_text(body.notes, "notes") if body.notes else None

    source = SourceText(title="[compare]", content=text, language="ja")
    session.add(source)
    await session.flush()

    translation = Translation(
        source_text_id=source.id,
        content="",
        model="compare",
        notes=notes,
        current_stage="pending",
    )
    session.add(translation)
    await session.commit()
    await session.refresh(translation)
    return {"job_id": translation.id}
