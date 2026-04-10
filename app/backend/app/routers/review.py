"""POST /api/v1/review — run the reader panel against a translation."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.reader_panel import ReaderPanel, ReviewFinding

router = APIRouter(prefix="/review", tags=["review"])

_panel = ReaderPanel()


class ReviewRequest(BaseModel):
    translation: str = Field(..., max_length=50_000)
    source: str | None = Field(default=None, max_length=50_000)
    paragraph_ids: list[int] | None = None
    auto_rerun: bool = False


class ReviewResponse(BaseModel):
    findings: list[ReviewFinding]
    rerun_triggered: bool = False


@router.post("", response_model=ReviewResponse)
async def review_translation(body: ReviewRequest) -> ReviewResponse:
    findings = await _panel.review(translation=body.translation, source=body.source)
    rerun = bool(body.auto_rerun and any(f.severity == "error" for f in findings))
    # Note: auto_rerun is acknowledged here but the actual re-translation is the
    # caller's responsibility (UI flow). We just signal whether one is warranted.
    return ReviewResponse(findings=findings, rerun_triggered=rerun)
