"""Glossary CRUD endpoints — /api/v1/books/{book_id}/glossary."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..services.glossary_service import GlossaryService, GlossaryTerm
from ..utils.sanitize import sanitize_text

router = APIRouter(prefix="/books/{book_id}/glossary", tags=["glossary"])


class TermIn(BaseModel):
    source_term: str
    target_term: str
    category: str | None = None
    notes: str | None = None
    is_locked: bool = False


class TermUpdate(BaseModel):
    target_term: str | None = None
    category: str | None = None
    notes: str | None = None
    is_locked: bool | None = None


class GlossaryResponse(BaseModel):
    glossary_id: int
    terms: list[GlossaryTerm]


@router.get("", response_model=GlossaryResponse)
async def list_glossary(
    book_id: int, session: AsyncSession = Depends(get_session),
) -> GlossaryResponse:
    svc = GlossaryService(session)
    g = await svc.get_or_create_for_book(book_id)
    terms = await svc.list_terms(g.id)
    return GlossaryResponse(glossary_id=g.id, terms=terms)


@router.post("/terms", response_model=GlossaryTerm)
async def add_term(
    book_id: int, body: TermIn,
    session: AsyncSession = Depends(get_session),
) -> GlossaryTerm:
    body.source_term = sanitize_text(body.source_term, "source_term")
    body.target_term = sanitize_text(body.target_term, "target_term")
    if body.notes:
        body.notes = sanitize_text(body.notes, "notes")
    svc = GlossaryService(session)
    g = await svc.get_or_create_for_book(book_id)
    return await svc.add_term(
        glossary_id=g.id, source_term=body.source_term, target_term=body.target_term,
        category=body.category, notes=body.notes, is_locked=body.is_locked,
    )


@router.put("/terms/{term_id}", response_model=GlossaryTerm)
async def update_term(
    book_id: int, term_id: int, body: TermUpdate,
    session: AsyncSession = Depends(get_session),
) -> GlossaryTerm:
    if body.target_term is not None:
        body.target_term = sanitize_text(body.target_term, "target_term")
    if body.notes is not None:
        body.notes = sanitize_text(body.notes, "notes")
    svc = GlossaryService(session)
    # V10: Verify term belongs to this book's glossary (BOLA prevention)
    g = await svc.get_or_create_for_book(book_id)
    updated = await svc.update_term(term_id, **body.model_dump(exclude_none=True))
    if updated is None or updated.glossary_id != g.id:
        raise HTTPException(status_code=404, detail="Term not found")
    return updated


@router.delete("/terms/{term_id}")
async def delete_term(
    book_id: int, term_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = GlossaryService(session)
    # V10: Verify term belongs to this book's glossary (BOLA prevention)
    g = await svc.get_or_create_for_book(book_id)
    term = await svc.get_term(term_id)
    if term is None or term.glossary_id != g.id:
        raise HTTPException(status_code=404, detail="Term not found")
    deleted = await svc.delete_term(term_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Term not found")
    return {"deleted": True}


class AutoExtractRequest(BaseModel):
    source_text: str
    translated_text: str


@router.post("/auto-extract", response_model=list[GlossaryTerm])
async def auto_extract(
    book_id: int, body: AutoExtractRequest,
    session: AsyncSession = Depends(get_session),
) -> list[GlossaryTerm]:
    body.source_text = sanitize_text(body.source_text, "source_text")
    body.translated_text = sanitize_text(body.translated_text, "translated_text")
    svc = GlossaryService(session)
    g = await svc.get_or_create_for_book(book_id)
    return await svc.auto_extract_from_translation(
        glossary_id=g.id, source_text=body.source_text, translated_text=body.translated_text,
    )
