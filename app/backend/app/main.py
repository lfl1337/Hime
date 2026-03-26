import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

_log = logging.getLogger(__name__)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import AsyncSessionLocal, init_db
from .middleware.audit import AuditMiddleware
from .middleware.rate_limit import limiter
from .routers import texts, translations, training
from .routers import epub as epub_router
from .routers import hardware as hardware_router
from .routers import compare as compare_router
from .routers import models as models_router
from .websocket import streaming
from .services.epub_service import get_setting, scan_watch_folder
from .services.hardware_monitor import cleanup_old_hardware_stats, get_hardware_stats, save_hardware_stats, vacuum_hardware_db

DEFAULT_WATCH_FOLDER = "C:/Projekte/Hime/data/epubs/"


async def _scan_loop() -> None:
    while True:
        await asyncio.sleep(60)
        _log.debug("EPUB scan starting...")
        t0 = time.perf_counter()
        async with AsyncSessionLocal() as session:
            folder = await get_setting("epub_watch_folder", session) or DEFAULT_WATCH_FOLDER
            await scan_watch_folder(folder, session)
        elapsed = time.perf_counter() - t0
        if elapsed > 10:
            _log.warning("EPUB scan took %.1fs (>10s)", elapsed)
        else:
            _log.debug("EPUB scan complete in %.2fs, next in 60s", elapsed)


async def _hardware_loop() -> None:
    _cleanup_counter = 0
    _vacuum_counter = 0
    while True:
        await asyncio.sleep(5)
        try:
            stats = await asyncio.to_thread(get_hardware_stats)
            await asyncio.to_thread(save_hardware_stats, stats)
        except Exception:
            pass
        _cleanup_counter += 1
        if _cleanup_counter >= 60:  # Every 5 minutes (60 × 5 s)
            _cleanup_counter = 0
            try:
                await asyncio.to_thread(cleanup_old_hardware_stats, hours=1)
            except Exception:
                pass
        _vacuum_counter += 1
        if _vacuum_counter >= 720:  # Every hour (720 × 5 s)
            _vacuum_counter = 0
            try:
                await asyncio.to_thread(vacuum_hardware_db)
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _log.info("FastAPI lifespan startup: DB init + watch folder scan")
    await init_db()
    # Initial scan on startup
    async with AsyncSessionLocal() as session:
        folder = await get_setting("epub_watch_folder", session) or DEFAULT_WATCH_FOLDER
        await scan_watch_folder(folder, session)
    # Background tasks
    scan_task = asyncio.create_task(_scan_loop())
    # hw_task disabled: hardware background collection stopped for stability (v0.8.0)
    # hw_task = asyncio.create_task(_hardware_loop())
    yield
    scan_task.cancel()
    with suppress(asyncio.CancelledError):
        await scan_task
    _log.info("FastAPI lifespan shutdown")


app = FastAPI(
    title="Hime Translation API",
    description="Local-first Japanese-to-English light novel translation",
    version="1.0.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def _log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    logging.getLogger("hime.requests").debug(
        "%s %s → %d (%dms)",
        request.method, request.url.path, response.status_code, round(ms),
    )
    return response


# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Audit logging — must come before CORS so every request is captured
app.add_middleware(AuditMiddleware, log_path=settings.audit_log_path)

# CORS — allow Tauri origins (dev + packaged) only
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",   # Tauri dev default
        "http://127.0.0.1:1420",
        "tauri://localhost",       # Packaged Tauri app (macOS/Linux)
        "http://tauri.localhost",  # Packaged Tauri app (Windows WebView2)
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Accept"],
)

# Routers
app.include_router(texts.router, prefix="/api/v1")
app.include_router(translations.router, prefix="/api/v1")
app.include_router(training.router, prefix="/api/v1")
app.include_router(epub_router.router, prefix="/api/v1")
app.include_router(hardware_router.router, prefix="/api/v1")
app.include_router(compare_router.router, prefix="/api/v1")
app.include_router(models_router.router, prefix="/api/v1")
app.include_router(streaming.router)  # WebSocket — no /api/v1 prefix


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness check — no auth required."""
    return {"status": "ok", "app": "hime", "version": "1.0.0"}
