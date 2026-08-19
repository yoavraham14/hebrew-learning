"""Startup bootstrap + in-process periodic top-up job (SPEC.md §2.4).

No external scheduler infrastructure — a single APScheduler background
thread inside the FastAPI process. This carries over cleanly to a container
running anywhere (including future k8s) as long as the process stays alive;
if it's ever run as multiple replicas, each replica runs its own top-up
check, and the daily call cap (shared via Postgres) is still the real
backstop against over-calling, not "only one instance runs the job".
"""

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.logging_config import get_logger
from app.models import Profile, UserWordProgress, WordPair
from app.services.word_generator import run_generation_batch, run_sentence_backfill_batch

logger = get_logger(__name__)


def bootstrap_if_empty() -> None:
    db = SessionLocal()
    try:
        total = db.scalar(select(func.count()).select_from(WordPair)) or 0
        if total == 0:
            logger.info("word bank is empty; running bootstrap generation batch")
            run_generation_batch(db)
    finally:
        db.close()


def _unseen_count_for_profile(db, profile_id: int) -> int:
    total = db.scalar(select(func.count()).select_from(WordPair)) or 0
    seen = (
        db.scalar(
            select(func.count())
            .select_from(UserWordProgress)
            .where(UserWordProgress.profile_id == profile_id)
        )
        or 0
    )
    return max(total - seen, 0)


def check_and_topup() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        profiles = db.scalars(select(Profile)).all()
        if not profiles:
            return
        low = [
            p.slug
            for p in profiles
            if _unseen_count_for_profile(db, p.id) < settings.topup_threshold
        ]
        if low:
            logger.info(
                "unseen word count below threshold; running top-up batch",
                extra={"extra_fields": {"profiles_below_threshold": low}},
            )
            run_generation_batch(db)

        # Opportunistic maintenance, independent of the unseen-word
        # threshold above — spreads the sentence-quality/transliteration
        # backfill across many small calls over natural top-up cycles
        # rather than a one-off burst script. Runs after the top-up check
        # so a genuine unseen-word shortage always gets first claim on the
        # shared daily cap; this just no-ops if the cap's already spent.
        run_sentence_backfill_batch(db)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        check_and_topup,
        trigger="interval",
        minutes=settings.topup_check_interval_minutes,
        id="topup_check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "top-up scheduler started",
        extra={"extra_fields": {"interval_minutes": settings.topup_check_interval_minutes}},
    )
    return scheduler
