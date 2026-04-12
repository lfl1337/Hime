"""GET /api/v1/lexicon/translate — algorithmic JP→EN literal translation."""
from fastapi import APIRouter, Query

from ..services.lexicon_service import LexiconResult, LexiconService

router = APIRouter(prefix="/lexicon", tags=["lexicon"])

_lexicon = LexiconService()


@router.get("/translate", response_model=LexiconResult)
async def lexicon_translate(text: str = Query(..., max_length=2000)) -> LexiconResult:
    # W5: Backend-only/CLI — no frontend caller as of v1.1.2; planned for tooltip lookups
    return _lexicon.translate(text)
