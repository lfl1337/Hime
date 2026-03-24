"""
API key authentication dependency.

Usage:
    @router.get("/endpoint")
    async def my_endpoint(_: str = Depends(require_api_key)):
        ...
"""
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


async def require_api_key(api_key: str = Security(_api_key_header)) -> str:
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return api_key
