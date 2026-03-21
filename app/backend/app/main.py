from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import init_db
from .middleware.audit import AuditMiddleware
from .middleware.rate_limit import limiter
from .routers import texts, translations, training
from .websocket import streaming


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    yield


app = FastAPI(
    title="Hime Translation API",
    description="Local-first Japanese-to-English light novel translation",
    version="0.2.3",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Audit logging — must come before CORS so every request is captured
app.add_middleware(AuditMiddleware, log_path=settings.audit_log_path)

# CORS — allow Tauri origins (dev + packaged) and any local port
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",   # Tauri dev default
        "http://127.0.0.1:1420",
        "tauri://localhost",       # Packaged Tauri app (macOS/Linux)
        "http://tauri.localhost",  # Packaged Tauri app (Windows WebView2)
    ],
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Routers
app.include_router(texts.router, prefix="/api/v1")
app.include_router(translations.router, prefix="/api/v1")
app.include_router(training.router, prefix="/api/v1")
app.include_router(streaming.router)  # WebSocket — no /api/v1 prefix


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness check — no auth required."""
    return {"status": "ok", "app": "hime", "version": "0.2.3"}
