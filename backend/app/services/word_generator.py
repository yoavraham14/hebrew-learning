"""Orchestrates one word-bank generation batch: cap/halt checks, topic/CEFR
rotation, the Gemini call, validation (already done inside gemini_client via
the Pydantic schema), dedup-on-insert, and call logging. See SPEC.md §2.

This module is the only thing allowed to call generate_word_batch — it is
where the cost firewall lives.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import GenerationCallLog, GenerationStatus, WordPair
from app.schemas import GeneratedWordItem
from app.services.gemini_client import (
    GeminiBillingError,
    GeminiGenerationError,
    generate_word_batch,
)

logger = get_logger(__name__)

TOPICS: list[str] = [
    "food",
    "travel",
    "family",
    "daily routine",
    "work",
    "emotions",
    "nature",
    "shopping",
    "health",
    "numbers and time",
    "home",
    "weather",
    "hobbies",
    "clothing",
    "transportation",
]
CEFR_LEVELS: list[str] = ["A1", "A2", "B1", "B2"]

_EXCLUSION_LIST_LIMIT = 300


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_status(db: Session) -> GenerationStatus:
    status = db.get(GenerationStatus, 1)
    if status is None:
        status = GenerationStatus(id=1, halted=False)
        db.add(status)
        db.commit()
        db.refresh(status)
    return status


def _count_calls_today(db: Session) -> int:
    now = _utcnow()
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    count = db.scalar(
        select(func.count())
        .select_from(GenerationCallLog)
        .where(GenerationCallLog.called_at >= start, GenerationCallLog.called_at < end)
    )
    return count or 0


def _pick_topic_and_level(db: Session) -> tuple[str, str]:
    total_calls = db.scalar(select(func.count()).select_from(GenerationCallLog)) or 0
    topic = TOPICS[total_calls % len(TOPICS)]
    level = CEFR_LEVELS[total_calls % len(CEFR_LEVELS)]
    return topic, level


def _get_exclusion_list(db: Session, limit: int = _EXCLUSION_LIST_LIMIT) -> list[str]:
    rows = db.scalars(select(WordPair.hebrew_word).order_by(WordPair.id.desc()).limit(limit)).all()
    return list(rows)


def _insert_words(db: Session, items: list[GeneratedWordItem]) -> int:
    """Insert validated items, skipping any already in the bank. Checks (and
    flushes) one at a time so duplicates *within* the same generated batch
    are also caught, not just duplicates against existing rows. The DB-level
    unique constraint on (hebrew_word, spanish_word) is the backstop against
    any race this misses.
    """
    inserted = 0
    for item in items:
        exists = db.scalar(
            select(WordPair.id).where(
                WordPair.hebrew_word == item.hebrew_word,
                WordPair.spanish_word == item.spanish_word,
            )
        )
        if exists is not None:
            continue
        db.add(WordPair(**item.model_dump()))
        db.flush()
        inserted += 1
    return inserted


def get_generation_health(db: Session) -> dict:
    """Read-only status for GET /ready — never triggers a call."""
    settings = get_settings()
    status = get_or_create_status(db)
    return {
        "halted": status.halted,
        "halted_reason": status.halted_reason,
        "halted_at": status.halted_at.isoformat() if status.halted_at else None,
        "last_success_at": status.last_success_at.isoformat() if status.last_success_at else None,
        "daily_call_count": _count_calls_today(db),
        "daily_call_cap": settings.gemini_daily_call_cap,
    }


def run_generation_batch(db: Session, *, batch_size: int | None = None) -> int:
    """Attempt one generation batch. Returns the number of new words
    inserted. Always fails safe: on cap/halt/error, returns 0 and never
    raises — callers (startup, scheduler) should not crash the app over a
    generation hiccup; the UI keeps serving from the existing bank either
    way (SPEC.md §2.1).
    """
    settings = get_settings()
    status = get_or_create_status(db)

    if status.halted:
        logger.warning(
            "generation halted; skipping batch",
            extra={"extra_fields": {"halted_reason": status.halted_reason}},
        )
        return 0

    daily_count = _count_calls_today(db)
    if daily_count >= settings.gemini_daily_call_cap:
        logger.info(
            "daily gemini call cap reached; serving from existing bank only",
            extra={"extra_fields": {"daily_count": daily_count, "cap": settings.gemini_daily_call_cap}},
        )
        return 0

    topic, level = _pick_topic_and_level(db)
    exclude = _get_exclusion_list(db)
    size = batch_size or settings.generation_batch_size

    try:
        batch = generate_word_batch(
            topic=topic, cefr_level=level, exclude_hebrew_words=exclude, batch_size=size
        )
    except GeminiBillingError as exc:
        status.halted = True
        status.halted_reason = str(exc)[:2000]
        status.halted_at = _utcnow()
        db.add(
            GenerationCallLog(
                called_at=_utcnow(),
                batch_size_requested=size,
                words_inserted=0,
                status="error",
                error_message=f"BILLING (halted generation): {exc}"[:2000],
            )
        )
        db.commit()
        logger.error(
            "gemini billing-related error — generation HALTED, needs manual review",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return 0
    except GeminiGenerationError as exc:
        db.add(
            GenerationCallLog(
                called_at=_utcnow(),
                batch_size_requested=size,
                words_inserted=0,
                status="error",
                error_message=str(exc)[:2000],
            )
        )
        db.commit()
        logger.warning("gemini generation call failed (will retry next cycle)", extra={"extra_fields": {"error": str(exc)}})
        return 0

    inserted = _insert_words(db, batch.words)
    status.last_success_at = _utcnow()
    db.add(
        GenerationCallLog(
            called_at=_utcnow(),
            batch_size_requested=size,
            words_inserted=inserted,
            status="success",
        )
    )
    db.commit()
    logger.info(
        "generated word batch",
        extra={
            "extra_fields": {
                "topic": topic,
                "cefr_level": level,
                "requested": size,
                "inserted": inserted,
            }
        },
    )
    return inserted
