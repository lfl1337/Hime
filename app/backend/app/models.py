from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class SourceText(Base):
    """A piece of Japanese source text to be translated."""

    __tablename__ = "source_texts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="ja")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    translations: Mapped[list["Translation"]] = relationship(
        back_populates="source_text", cascade="all, delete-orphan"
    )


class Translation(Base):
    """An English translation of a SourceText, produced by a model."""

    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_text_id: Mapped[int] = mapped_column(
        ForeignKey("source_texts.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # Pipeline outputs — populated stage by stage; None until each stage completes
    stage1_gemma_output:    Mapped[str | None] = mapped_column(Text, nullable=True)
    stage1_deepseek_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage1_qwen32b_output:  Mapped[str | None] = mapped_column(Text, nullable=True)
    consensus_output:       Mapped[str | None] = mapped_column(Text, nullable=True)
    stage2_output:          Mapped[str | None] = mapped_column(Text, nullable=True)
    final_output:           Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_duration_ms:   Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pending | stage1 | consensus | stage2 | stage3 | complete | error
    current_stage:          Mapped[str | None] = mapped_column(String(32), nullable=True)

    source_text: Mapped["SourceText"] = relationship(back_populates="translations")
