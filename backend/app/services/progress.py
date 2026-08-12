from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyActivity, Profile, UserWordProgress, WordPair
from app.schemas import ProgressOut


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

    return ProgressOut(
        words_seen=words_seen,
        words_fluent=words_fluent,
        total_verified_words=total_verified_words,
        current_streak=profile.current_streak,
        longest_streak=profile.longest_streak,
        due_today=due_today,
        daily_goal=profile.daily_goal,
        today_review_count=today_review_count,
    )
