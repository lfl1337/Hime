"""
Shared slowapi limiter instance.

Defined here so both main.py (which registers the exception handler and
attaches the limiter to app.state) and individual routers (which use the
@limiter.limit decorator) can import from the same object without creating
circular imports.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)
