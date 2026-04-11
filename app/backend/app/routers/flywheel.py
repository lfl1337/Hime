"""POST /api/v1/training/flywheel/export — export reviewed translations as training data."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..services.flywheel_service import FlywheelService

router = APIRouter(prefix="/training/flywheel", tags=["flywheel"])


class FlywheelExportRequest(BaseModel):
    min_quality: float = Field(default=0.8, ge=0.0, le=1.0)


class FlywheelExportResponse(BaseModel):
    new_entries: int


@router.post("/export", response_model=FlywheelExportResponse)
async def export(
    body: FlywheelExportRequest,
    session: AsyncSession = Depends(get_session),
) -> FlywheelExportResponse:
    # W5: Backend-only/CLI — no frontend caller as of v1.1.2; planned for training flywheel UI
    svc = FlywheelService(session)
    count = await svc.export_reviewed_to_training_data(min_quality=body.min_quality)
    return FlywheelExportResponse(new_entries=count)
