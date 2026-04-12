from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
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
    confidence_log:         Mapped[str | None] = mapped_column(Text, nullable=True)

    source_text: Mapped["SourceText"] = relationship(back_populates="translations")


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    cover_image_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_chapters: Mapped[int] = mapped_column(Integer, default=0)
    total_paragraphs: Mapped[int] = mapped_column(Integer, default=0)
    translated_paragraphs: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="not_started")
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    chapters: Mapped[list["Chapter"]] = relationship(back_populates="book", cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    total_paragraphs: Mapped[int] = mapped_column(Integer, default=0)
    translated_paragraphs: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="not_started")
    is_front_matter: Mapped[bool] = mapped_column(Boolean, default=False)
    book: Mapped["Book"] = relationship(back_populates="chapters")
    paragraphs: Mapped[list["Paragraph"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")


class Paragraph(Base):
    __tablename__ = "paragraphs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    translated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v2.0.0 — Stage 4 retry mechanism
    retry_count_fix_pass: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    retry_count_full_pipeline: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    retry_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    aggregator_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    aggregator_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapter: Mapped["Chapter"] = relationship(back_populates="paragraphs")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Glossary(Base):
    __tablename__ = "glossaries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    glossary_id: Mapped[int] = mapped_column(ForeignKey("glossaries.id"), nullable=False)
    source_term: Mapped[str] = mapped_column(Text, nullable=False)
    target_term: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrences: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
