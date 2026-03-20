from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Source texts
# ---------------------------------------------------------------------------

class SourceTextCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="ja", pattern=r"^[a-z]{2,10}$")


class SourceTextRead(BaseModel):
    id: int
    title: str
    content: str
    language: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

class TranslateRequest(BaseModel):
    """Request to translate a stored SourceText."""

    source_text_id: int
    # If omitted, the backend falls back to settings.inference_model
    model: str | None = Field(default=None, max_length=128)
    # Optional translator notes / style hints passed to the model as system prompt additions
    notes: str | None = Field(default=None, max_length=2_000)


class TranslationRead(BaseModel):
    id: int
    source_text_id: int
    content: str
    model: str
    notes: str | None
    created_at: datetime
    # Pipeline fields — None until each stage completes
    stage1_gemma_output:    str | None = None
    stage1_deepseek_output: str | None = None
    stage1_qwen32b_output:  str | None = None
    consensus_output:       str | None = None
    stage2_output:          str | None = None
    final_output:           str | None = None
    pipeline_duration_ms:   int | None = None
    current_stage:          str | None = None

    model_config = {"from_attributes": True}


class TranslateJobResponse(BaseModel):
    """Returned by POST /translate when the pipeline job is created (202)."""
    job_id: int


class PipelineStatusRead(BaseModel):
    """Lightweight status poll response."""
    job_id: int
    current_stage: str | None
    pipeline_duration_ms: int | None
    final_output: str | None

    model_config = {"from_attributes": True}
