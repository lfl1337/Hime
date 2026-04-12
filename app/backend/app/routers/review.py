"""POST /api/v1/review — run the reader panel against a translation."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..middleware.rate_limit import limiter
from ..services.reader_panel import ReaderPanel, ReviewFinding
from ..utils.sanitize import sanitize_text

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
@limiter.limit("10/minute")
async def review_translation(request: Request, body: ReviewRequest) -> ReviewResponse:
    translation = sanitize_text(body.translation, field_name="translation")
    source = sanitize_text(body.source, field_name="source") if body.source is not None else None
    findings = await _panel.review(translation=translation, source=source)
    rerun = bool(body.auto_rerun and any(f.severity == "error" for f in findings))
    # Note: auto_rerun is acknowledged here but the actual re-translation is the
    # caller's responsibility (UI flow). We just signal whether one is warranted.
    return ReviewResponse(findings=findings, rerun_triggered=rerun)
