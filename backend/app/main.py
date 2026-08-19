from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.routers import audio, auth, cards, health, internal, profiles, progress, videos
from app.services.scheduler import bootstrap_if_empty, start_scheduler

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)

# Populated only inside the production container (see Dockerfile — the
# built frontend's dist/ is copied to /app/static, and this file lives at
# /app/app/main.py, so parent.parent is /app regardless of the process's
# cwd). Absent in local dev, where Vite's own dev server serves the
# frontend instead — everything below is skipped in that case.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting up")
    bootstrap_if_empty()
    scheduler = start_scheduler() if settings.enable_in_process_scheduler else None
    if scheduler is None:
        logger.info("in-process scheduler disabled — relying on external task triggers (e.g. Cloud Scheduler)")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("shut down")


app = FastAPI(title="Lingua — Bilingual Vocabulary Trainer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers first — the SPA catch-all below is registered last and only
# ever matches what nothing above it already claimed.
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(cards.router)
app.include_router(progress.router)
app.include_router(audio.router)
app.include_router(internal.router)
app.include_router(videos.router)

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        """Single-container deploy (Cloud Run): this process serves both the
        API and the built React app. Any path not already matched by an API
        router above falls through to here and gets index.html, so
        client-side routes survive a hard refresh instead of 404ing.
        """
        return FileResponse(STATIC_DIR / "index.html")
