"""GET /api/v1/lexicon/translate — algorithmic JP→EN literal translation."""
from fastapi import APIRouter, Query

from ..services.lexicon_service import LexiconResult, LexiconService

router = APIRouter(prefix="/lexicon", tags=["lexicon"])

_lexicon = LexiconService()


@router.get("/translate", response_model=LexiconResult)
async def lexicon_translate(text: str = Query(..., max_length=2000)) -> LexiconResult:
    return _lexicon.translate(text)
