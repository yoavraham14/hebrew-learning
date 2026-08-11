from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Profile, UserWordProgress
from app.schemas import ProgressOut
from app.services.review import KNOWN_BOX_THRESHOLD


def get_progress(db: Session, profile: Profile) -> ProgressOut:
    words_seen = (
        db.scalar(
            select(func.count()).select_from(UserWordProgress).where(UserWordProgress.profile_id == profile.id)
        )
        or 0
    )
    words_known = (
        db.scalar(
            select(func.count())
            .select_from(UserWordProgress)
            .where(
                UserWordProgress.profile_id == profile.id,
                UserWordProgress.box >= KNOWN_BOX_THRESHOLD,
            )
        )
        or 0
    )
    return ProgressOut(
        words_seen=words_seen,
        words_known=words_known,
        current_streak=profile.current_streak,
    )
