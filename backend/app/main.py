from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.routers import audio, auth, cards, health, profiles, progress
from app.services.scheduler import bootstrap_if_empty, start_scheduler

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting up")
    bootstrap_if_empty()
    scheduler = start_scheduler()
    yield
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

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(cards.router)
app.include_router(progress.router)
app.include_router(audio.router)
