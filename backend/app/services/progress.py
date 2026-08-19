from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyActivity, Profile, UserWordProgress, WatchedVideo, WordPair
from app.schemas import ActivityDayOut, ProgressOut, WeeklySummaryOut, WordProgressOut
from app.services.cards import get_or_create_progress


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_progress(db: Session, profile: Profile) -> ProgressOut:
    now = _utcnow()

    words_seen = (
        db.scalar(
            select(func.count()).select_from(UserWordProgress).where(UserWordProgress.profile_id == profile.id)
        )
        or 0
    )
    words_fluent = (
        db.scalar(
            select(func.count())
            .select_from(UserWordProgress)
            .where(UserWordProgress.profile_id == profile.id, UserWordProgress.status == "fluent")
        )
        or 0
    )
    total_verified_words = db.scalar(select(func.count()).select_from(WordPair).where(WordPair.verified.is_(True))) or 0

    # Matches get_next_card's due-review filter exactly (excludes fluent —
    # those aren't part of the normal deck this count is describing).
    due_today = (
        db.scalar(
            select(func.count())
            .select_from(UserWordProgress)
            .where(
                UserWordProgress.profile_id == profile.id,
                UserWordProgress.next_review_at <= now,
                UserWordProgress.status != "fluent",
            )
        )
        or 0
    )

    today_activity = db.scalar(
        select(DailyActivity).where(
            DailyActivity.profile_id == profile.id, DailyActivity.activity_date == now.date()
        )
    )
    today_review_count = today_activity.review_count if today_activity else 0

    videos_watched = (
        db.scalar(select(func.count()).select_from(WatchedVideo).where(WatchedVideo.profile_id == profile.id)) or 0
    )
    # Same rolling 7-day window as get_weekly_summary below — one shared
    # "this week" convention across the progress page.
    week_start = now.date() - timedelta(days=6)
    videos_watched_this_week = (
        db.scalar(
            select(func.count())
            .select_from(WatchedVideo)
            .where(
                WatchedVideo.profile_id == profile.id,
                func.date(WatchedVideo.watched_at) >= week_start,
            )
        )
        or 0
    )

    return ProgressOut(
        words_seen=words_seen,
        words_fluent=words_fluent,
        total_verified_words=total_verified_words,
        current_streak=profile.current_streak,
        longest_streak=profile.longest_streak,
        due_today=due_today,
        daily_goal=profile.daily_goal,
        today_review_count=today_review_count,
        videos_watched=videos_watched,
        videos_watched_this_week=videos_watched_this_week,
        weekly_video_goal=profile.weekly_video_goal,
    )


def _to_word_progress_out(progress: UserWordProgress) -> WordProgressOut:
    accuracy = (progress.times_correct / progress.times_seen * 100) if progress.times_seen > 0 else 0.0
    wp = progress.word_pair
    return WordProgressOut(
        word_pair_id=wp.id,
        hebrew_word=wp.hebrew_word,
        spanish_word=wp.spanish_word,
        english_word=wp.english_word,
        phonetic_es=wp.phonetic_es,
        topic=wp.topic,
        cefr_level=wp.cefr_level,
        status=progress.status,
        starred=progress.starred,
        times_seen=progress.times_seen,
        times_correct=progress.times_correct,
        accuracy=round(accuracy, 1),
        fluent_at=progress.fluent_at,
    )


def list_word_progress(db: Session, profile: Profile) -> list[WordProgressOut]:
    """Every word this profile has seen — the word table's data source.
    Flat list; sorting/searching happens client-side (see schemas.py's
    module docstring for why).
    """
    rows = db.scalars(
        select(UserWordProgress)
        .where(UserWordProgress.profile_id == profile.id)
        .order_by(UserWordProgress.word_pair_id.asc())
    ).all()
    return [_to_word_progress_out(row) for row in rows]


def _get_progress_row_or_404(db: Session, profile: Profile, word_pair_id: int) -> UserWordProgress:
    progress = db.scalar(
        select(UserWordProgress).where(
            UserWordProgress.profile_id == profile.id, UserWordProgress.word_pair_id == word_pair_id
        )
    )
    if progress is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="word not seen by this profile yet")
    return progress


def mark_fluent(db: Session, profile: Profile, word_pair_id: int) -> WordProgressOut:
    """Manual override from the word table — immediately fluent regardless
    of `repetitions` vs. the threshold. Not a permanent exemption: if this
    word is later pulled into a mixed round and missed, the normal
    recompute-on-every-rating logic in cards._apply_result applies exactly
    as it would for an organically-fluent word.
    """
    progress = _get_progress_row_or_404(db, profile, word_pair_id)
    if progress.status != "fluent":
        progress.status = "fluent"
        progress.fluent_at = _utcnow()
    db.commit()
    db.refresh(progress)
    return _to_word_progress_out(progress)


def reset_word(db: Session, profile: Profile, word_pair_id: int) -> WordProgressOut:
    """Zeroes this word's learning stats back to a fresh, never-studied
    state — but keeps the row (still appears in the word table) and
    leaves `starred` untouched, since starring is a preference, not
    learning progress. This is the per-word reset (word table); the
    full-profile reset (settings, password-protected) is a separate,
    genuinely destructive operation — see reset_profile.
    """
    progress = _get_progress_row_or_404(db, profile, word_pair_id)
    now = _utcnow()
    progress.box = 0
    progress.repetitions = 0
    progress.ease_factor = 2.5
    progress.interval_days = 0
    progress.next_review_at = now
    progress.last_result = None
    progress.times_seen = 0
    progress.times_correct = 0
    progress.exercise_level = 0
    progress.exercise_level_streak = 0
    progress.status = "new"
    progress.fluent_at = None
    db.commit()
    db.refresh(progress)
    return _to_word_progress_out(progress)


def set_starred(db: Session, profile: Profile, word_pair_id: int, starred: bool) -> WordProgressOut:
    """Usable from either the study card (a word may not have a progress
    row yet — lazily created, same as a first rating would) or the word
    table (row already exists)."""
    progress = get_or_create_progress(db, profile, word_pair_id, _utcnow())
    progress.starred = starred
    db.commit()
    db.refresh(progress)
    return _to_word_progress_out(progress)


# ---------------------------------------------------------------------------
# Activity calendar + weekly summary (stage E) — both read DailyActivity,
# no new table.
# ---------------------------------------------------------------------------


def get_activity(db: Session, profile: Profile, *, days: int = 365) -> list[ActivityDayOut]:
    """Daily activity for the last `days` days — the GitHub-style
    contribution grid's data source. Only returns days that actually have a
    row (i.e. had at least one review); the frontend fills in the gaps as
    zero, so an empty list is a valid ("never studied") response, not an
    error.
    """
    cutoff = _utcnow().date() - timedelta(days=days)
    rows = db.scalars(
        select(DailyActivity)
        .where(DailyActivity.profile_id == profile.id, DailyActivity.activity_date >= cutoff)
        .order_by(DailyActivity.activity_date.asc())
    ).all()
    return [ActivityDayOut.model_validate(row) for row in rows]


def get_weekly_summary(db: Session, profile: Profile) -> WeeklySummaryOut:
    """Past 7 days vs. the 7 before that (for the accuracy trend) — kept
    deliberately simple: a handful of counts, not a dashboard. See
    schemas.WeeklySummaryOut's accuracy fields for why 0.0 isn't an error.
    """
    today = _utcnow().date()
    this_week_start = today - timedelta(days=6)  # 7 days inclusive of today
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = this_week_start - timedelta(days=1)

    words_added = (
        db.scalar(
            select(func.count())
            .select_from(UserWordProgress)
            .where(
                UserWordProgress.profile_id == profile.id,
                UserWordProgress.first_seen_at.is_not(None),
                func.date(UserWordProgress.first_seen_at) >= this_week_start,
            )
        )
        or 0
    )
    words_became_fluent = (
        db.scalar(
            select(func.count())
            .select_from(UserWordProgress)
            .where(
                UserWordProgress.profile_id == profile.id,
                UserWordProgress.fluent_at.is_not(None),
                func.date(UserWordProgress.fluent_at) >= this_week_start,
            )
        )
        or 0
    )

    this_week_rows = db.scalars(
        select(DailyActivity).where(
            DailyActivity.profile_id == profile.id, DailyActivity.activity_date >= this_week_start
        )
    ).all()
    last_week_rows = db.scalars(
        select(DailyActivity).where(
            DailyActivity.profile_id == profile.id,
            DailyActivity.activity_date >= last_week_start,
            DailyActivity.activity_date <= last_week_end,
        )
    ).all()

    days_studied = sum(1 for r in this_week_rows if r.review_count > 0)
    reviews_this_week = sum(r.review_count for r in this_week_rows)
    correct_this_week = sum(r.correct_count for r in this_week_rows)
    reviews_last_week = sum(r.review_count for r in last_week_rows)
    correct_last_week = sum(r.correct_count for r in last_week_rows)

    accuracy_this_week = round(correct_this_week / reviews_this_week * 100, 1) if reviews_this_week > 0 else 0.0
    accuracy_last_week = round(correct_last_week / reviews_last_week * 100, 1) if reviews_last_week > 0 else 0.0

    return WeeklySummaryOut(
        words_added=words_added,
        words_became_fluent=words_became_fluent,
        days_studied=days_studied,
        reviews_this_week=reviews_this_week,
        accuracy_this_week=accuracy_this_week,
        accuracy_last_week=accuracy_last_week,
    )
