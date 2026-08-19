"""Orchestrates one word-bank generation batch: cap/halt checks, topic/CEFR
rotation, the two-stage Gemini pipeline (generate, then verify), dedup-on-
insert, and call logging. See SPEC.md §2 and the translation-verification
feature notes in the plan history.

This module is the only thing allowed to call generate_word_batch /
verify_word_batch — it is where the cost firewall lives.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import GenerationCallLog, GenerationStatus, WordPair
from app.schemas import GeneratedWordItem, SentenceBackfillItem, VerificationItem
from app.services.gemini_client import (
    CURRENT_SENTENCE_RULES_VERSION,
    GeminiBillingError,
    GeminiGenerationError,
    generate_word_batch,
    regenerate_sentence_batch,
    verify_sentence_backfill_batch,
    verify_word_batch,
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

SENTENCE_BACKFILL_BATCH_SIZE = 10


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
    """Sums `api_calls_made`, not row count — a single run_generation_batch
    call can make up to 2 real Gemini requests (generate + verify), and both
    must count against the daily cap.
    """
    now = _utcnow()
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    total = db.scalar(
        select(func.coalesce(func.sum(GenerationCallLog.api_calls_made), 0)).where(
            GenerationCallLog.called_at >= start, GenerationCallLog.called_at < end
        )
    )
    return total or 0


def _pick_topic_and_level(db: Session) -> tuple[str, str]:
    total_calls = db.scalar(select(func.count()).select_from(GenerationCallLog)) or 0
    topic = TOPICS[total_calls % len(TOPICS)]
    level = CEFR_LEVELS[total_calls % len(CEFR_LEVELS)]
    return topic, level


def _get_exclusion_list(db: Session, limit: int = _EXCLUSION_LIST_LIMIT) -> list[str]:
    rows = db.scalars(select(WordPair.hebrew_word).order_by(WordPair.id.desc()).limit(limit)).all()
    return list(rows)


def _halt(status: GenerationStatus, exc: Exception) -> None:
    status.halted = True
    status.halted_reason = str(exc)[:2000]
    status.halted_at = _utcnow()
    logger.error(
        "gemini billing-related error — generation HALTED, needs manual review",
        extra={"extra_fields": {"error": str(exc)}},
    )


def _insert_words_with_verification(
    db: Session,
    items: list[GeneratedWordItem],
    verification: dict[int, VerificationItem] | None,
) -> tuple[int, int]:
    """Insert the final (possibly corrected) content per item, skipping
    anything already in the bank (checked — and flushed — one at a time so
    in-batch duplicates are caught too, same as before this feature). Dedup
    runs against the FINAL text, so a correction that happens to match an
    existing row is skipped rather than double-inserted.

    `verification` is None when stage 2 didn't run at all (cap reached
    between stages, or itself failed) — every item is inserted unverified in
    that case, exactly as if each had gotten a "reject"-shaped non-result;
    they simply sit in the bank until a future generation run's verification
    pass happens to reconsider them, or a manual sweep does.

    Returns (inserted_count, verified_ok_count).
    """
    inserted = 0
    verified_ok = 0
    for idx, item in enumerate(items):
        result = verification.get(idx) if verification is not None else None

        if result is None:
            final_item, verified, note = item, False, (
                "not verified: verification call unavailable this run"
                if verification is None
                else "not verified: missing from verification response"
            )
        elif result.status == "ok":
            final_item, verified, note = item, True, result.note or "ok"
        elif result.status == "corrected" and result.corrected is not None:
            final_item, verified, note = result.corrected, True, result.note or "corrected by verification pass"
        else:  # "reject", or malformed "corrected" with no payload
            final_item, verified, note = item, False, result.note or "rejected by verification pass"

        if verified:
            verified_ok += 1

        exists = db.scalar(
            select(WordPair.id).where(
                WordPair.hebrew_word == final_item.hebrew_word,
                WordPair.spanish_word == final_item.spanish_word,
            )
        )
        if exists is not None:
            continue

        # sentence_rules_version is stamped as CURRENT regardless of
        # `verified` — that flag is about translation-naturalness, an
        # orthogonal axis to the specificity-rules version. Whatever
        # sentence Gemini produced this call was written under the
        # CURRENT prompt either way, so it's already current, not
        # something the sentence-backfill pass needs to revisit.
        db.add(
            WordPair(
                **final_item.model_dump(),
                verified=verified,
                verification_note=note,
                sentence_rules_version=CURRENT_SENTENCE_RULES_VERSION,
                sentence_source="generated",
            )
        )
        db.flush()
        inserted += 1

    return inserted, verified_ok


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

    Makes up to two real Gemini calls (generate, then verify) — both are
    gated by the daily cap independently, both count toward it, and either
    one hitting a billing-related error halts generation entirely.
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

    # --- Stage 1: generate ---
    try:
        batch = generate_word_batch(
            topic=topic, cefr_level=level, exclude_hebrew_words=exclude, batch_size=size
        )
    except GeminiBillingError as exc:
        _halt(status, exc)
        db.add(
            GenerationCallLog(
                called_at=_utcnow(),
                batch_size_requested=size,
                words_inserted=0,
                status="error",
                error_message=f"BILLING (halted generation): {exc}"[:2000],
                api_calls_made=1,
                verify_status=None,
            )
        )
        db.commit()
        return 0
    except GeminiGenerationError as exc:
        db.add(
            GenerationCallLog(
                called_at=_utcnow(),
                batch_size_requested=size,
                words_inserted=0,
                status="error",
                error_message=str(exc)[:2000],
                api_calls_made=1,
                verify_status=None,
            )
        )
        db.commit()
        logger.warning(
            "gemini generation call failed (will retry next cycle)",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return 0

    # --- Stage 2: verify (a second real call — re-check the cap first) ---
    api_calls_made = 1
    verify_status = "skipped_cap"
    verification_results: dict[int, VerificationItem] | None = None
    halted_mid_batch = False

    if daily_count + api_calls_made < settings.gemini_daily_call_cap:
        try:
            verification = verify_word_batch(items=batch.words, topic=topic, cefr_level=level)
            api_calls_made = 2
            verify_status = "success"
            verification_results = {r.index: r for r in verification.results}
        except GeminiBillingError as exc:
            api_calls_made = 2  # the call was made and errored — still counts
            verify_status = "error"
            _halt(status, exc)
            halted_mid_batch = True
        except GeminiGenerationError as exc:
            api_calls_made = 2
            verify_status = "error"
            logger.warning(
                "gemini verification call failed — inserting stage-1 words unverified",
                extra={"extra_fields": {"error": str(exc)}},
            )
    else:
        logger.info("skipping verification call this run — would exceed daily cap")

    # Insert regardless of stage-2 outcome — unverified words just sit in
    # the bank unselected until a future run verifies them (SPEC.md-adjacent
    # design; see plan decision on grandfathering/fail-safe insert).
    inserted, verified_ok = _insert_words_with_verification(db, batch.words, verification_results)
    status.last_success_at = _utcnow()
    db.add(
        GenerationCallLog(
            called_at=_utcnow(),
            batch_size_requested=size,
            words_inserted=inserted,
            status="success",
            api_calls_made=api_calls_made,
            verify_status=verify_status,
            words_verified_ok=verified_ok,
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
                "verified_ok": verified_ok,
                "api_calls_made": api_calls_made,
                "halted_after_verify": halted_mid_batch,
            }
        },
    )
    return inserted


def run_sentence_backfill_batch(db: Session, *, batch_size: int | None = None) -> int:
    """Regenerates example_sentence_he/_es/_phonetic_es for existing
    WordPair rows whose sentence was written under an older version of the
    specificity rules (SPEC.md-adjacent — see the review-games/sentence-
    round plan). Selected by `sentence_rules_version <
    CURRENT_SENTENCE_RULES_VERSION` — NOT by `example_sentence_phonetic_es
    IS NULL`: a row can already have a populated phonetic sentence from an
    OLDER, weaker version of the rules and still need reprocessing once
    those rules tighten (this is exactly what happened going from v0 to
    v1 — see gemini_client.CURRENT_SENTENCE_RULES_VERSION's docstring). No
    separate progress table; the version column itself is the work queue,
    and a version bump is what makes every row eligible again.

    Mirrors run_generation_batch's two-stage (generate, then verify) shape
    and cap/halt gating, but with a stricter apply rule: a regenerated
    sentence is only ever written to the row once verification actually
    confirms it ("ok" or "corrected"). If stage 2 is skipped (would exceed
    the daily cap), errors, or rejects an entry, that row is left
    untouched at NULL and retried on a future top-up cycle — unlike
    run_generation_batch, which inserts unverified new words anyway
    (the bank still needs them), here the OLD sentence already exists and
    works fine as a fallback, so there's never a reason to apply an
    unconfirmed rewrite. This is deliberately spread across many small
    calls via the periodic top-up scheduler (see
    app.services.scheduler.check_and_topup) rather than one burst script.

    Always fails safe: on cap/halt/error, returns 0 and never raises, same
    posture as run_generation_batch.
    """
    settings = get_settings()
    status = get_or_create_status(db)

    if status.halted:
        logger.warning(
            "generation halted; skipping sentence-backfill batch",
            extra={"extra_fields": {"halted_reason": status.halted_reason}},
        )
        return 0

    daily_count = _count_calls_today(db)
    if daily_count >= settings.gemini_daily_call_cap:
        logger.info(
            "daily gemini call cap reached; skipping sentence-backfill batch",
            extra={"extra_fields": {"daily_count": daily_count, "cap": settings.gemini_daily_call_cap}},
        )
        return 0

    size = batch_size or SENTENCE_BACKFILL_BATCH_SIZE
    rows = db.scalars(
        select(WordPair)
        .where(WordPair.sentence_rules_version < CURRENT_SENTENCE_RULES_VERSION)
        .order_by(WordPair.id.asc())
        .limit(size)
    ).all()
    if not rows:
        return 0

    items = [
        SentenceBackfillItem(
            word_pair_id=w.id,
            hebrew_word=w.hebrew_word,
            spanish_word=w.spanish_word,
            english_word=w.english_word,
            part_of_speech=w.part_of_speech,
            topic=w.topic,
            cefr_level=w.cefr_level,
            example_sentence_he=w.example_sentence_he,
            example_sentence_es=w.example_sentence_es,
        )
        for w in rows
    ]

    # --- Stage 1: regenerate ---
    try:
        batch = regenerate_sentence_batch(items)
    except GeminiBillingError as exc:
        _halt(status, exc)
        db.add(
            GenerationCallLog(
                called_at=_utcnow(),
                batch_size_requested=size,
                words_inserted=0,
                status="error",
                error_message=f"BILLING (halted generation): {exc}"[:2000],
                api_calls_made=1,
                verify_status=None,
                call_kind="sentence_backfill",
            )
        )
        db.commit()
        return 0
    except GeminiGenerationError as exc:
        db.add(
            GenerationCallLog(
                called_at=_utcnow(),
                batch_size_requested=size,
                words_inserted=0,
                status="error",
                error_message=str(exc)[:2000],
                api_calls_made=1,
                verify_status=None,
                call_kind="sentence_backfill",
            )
        )
        db.commit()
        logger.warning(
            "gemini sentence-backfill call failed (will retry next cycle)",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return 0

    # --- Stage 2: verify (re-check the cap first, same as run_generation_batch) ---
    api_calls_made = 1
    verify_status = "skipped_cap"
    verification_results: dict[int, object] | None = None

    if daily_count + api_calls_made < settings.gemini_daily_call_cap:
        try:
            verification = verify_sentence_backfill_batch(items=items, results=batch.results)
            api_calls_made = 2
            verify_status = "success"
            verification_results = {r.word_pair_id: r for r in verification.results}
        except GeminiBillingError as exc:
            api_calls_made = 2
            verify_status = "error"
            _halt(status, exc)
        except GeminiGenerationError as exc:
            api_calls_made = 2
            verify_status = "error"
            logger.warning(
                "gemini sentence-backfill verification call failed — no rows applied this run",
                extra={"extra_fields": {"error": str(exc)}},
            )
    else:
        logger.info("skipping sentence-backfill verification call this run — would exceed daily cap")

    # Only apply rows verification actually confirmed — see docstring for why
    # this is stricter than run_generation_batch's insert-anyway policy.
    updated = 0
    if verification_results is not None:
        results_by_id = {r.word_pair_id: r for r in batch.results}
        for w in rows:
            v = verification_results.get(w.id)
            if v is None or v.status == "reject":
                continue
            final = v.corrected if v.status == "corrected" else results_by_id.get(w.id)
            if final is None:
                continue
            w.example_sentence_he = final.example_sentence_he
            w.example_sentence_es = final.example_sentence_es
            w.example_sentence_phonetic_es = final.example_sentence_phonetic_es
            w.sentence_rules_version = CURRENT_SENTENCE_RULES_VERSION
            w.sentence_source = "gemini_backfill"
            updated += 1

    status.last_success_at = _utcnow()
    db.add(
        GenerationCallLog(
            called_at=_utcnow(),
            batch_size_requested=size,
            words_inserted=updated,
            status="success",
            api_calls_made=api_calls_made,
            verify_status=verify_status,
            words_verified_ok=updated,
            call_kind="sentence_backfill",
        )
    )
    db.commit()
    logger.info(
        "ran sentence-backfill batch",
        extra={
            "extra_fields": {
                "requested": size,
                "updated": updated,
                "api_calls_made": api_calls_made,
                "verify_status": verify_status,
            }
        },
    )
    return updated
