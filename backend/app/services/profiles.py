"""Add-user (self-service profile creation) and the full-profile reset —
progress-page feature pass, stage G. Both are deliberately separate from
routers/profiles.py's existing settings-update logic: these two are
higher-stakes (creates a new identity / destroys all progress for one),
so they get their own module rather than being folded into the same thin
inline handlers as PATCH /me.
"""

import re
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DailyActivity, Profile, RecentMiss, UserWordProgress
from app.schemas import Direction
from app.security import hash_pin

_DIRECTION_LANGS: dict[Direction, tuple[str, str]] = {
    # direction -> (native_lang, target_lang)
    "hebrew_learner": ("es", "he"),
    "spanish_learner": ("he", "es"),
}


def _slugify(display_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", display_name.strip().lower()).strip("_")
    return base or "profile"


def create_profile(db: Session, *, display_name: str, pin: str, direction: Direction) -> Profile:
    """Self-service, but NOT public/unauthenticated — the router requires
    an existing valid profile session to call this (SPEC.md §3's "no public
    signup" softened to "no signup without already having access", not
    reopened to the whole internet).
    """
    native_lang, target_lang = _DIRECTION_LANGS[direction]

    base_slug = _slugify(display_name)
    slug = base_slug
    suffix = 1
    while db.scalar(select(Profile).where(Profile.slug == slug)) is not None:
        suffix += 1
        slug = f"{base_slug}_{suffix}"

    profile = Profile(
        slug=slug,
        display_name=display_name,
        native_lang=native_lang,
        target_lang=target_lang,
        pin_hash=hash_pin(pin),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def reset_profile(db: Session, *, target_slug: str, password: str, confirmation: str) -> Profile:
    """Genuine full wipe for one profile: every UserWordProgress,
    RecentMiss, and DailyActivity row deleted, all counters zeroed. The
    Profile row itself (slug, PIN, display name, direction, and settings
    like fluency_threshold/daily_goal) is untouched — this can't lock
    anyone out of their own account, it only erases what they've studied.

    Two independent gates, both required: the shared RESET_PASSWORD (an
    operator-level secret, not the profile's own PIN — see config.py) and
    a literal "RESET" confirmation string, enforced here server-side, not
    just as a frontend nicety.
    """
    settings = get_settings()
    if not secrets.compare_digest(password, settings.reset_password):
        # 403, not 401: the caller IS authenticated (a valid profile JWT got
        # them this far) — this is a separate authorization gate they
        # failed, not an identity problem. Confirmed live: the frontend's
        # api/client.ts treats ANY 401 as "session expired" and force-clears
        # the JWT — a wrong reset password was silently logging people out
        # with a misleading message instead of just saying the password was
        # wrong. 403 doesn't trigger that interceptor.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="incorrect reset password")
    if confirmation != "RESET":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail='confirmation must be exactly "RESET"')

    profile = db.scalar(select(Profile).where(Profile.slug == target_slug))
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="profile not found")

    db.query(UserWordProgress).filter(UserWordProgress.profile_id == profile.id).delete()
    db.query(RecentMiss).filter(RecentMiss.profile_id == profile.id).delete()
    db.query(DailyActivity).filter(DailyActivity.profile_id == profile.id).delete()

    profile.total_reviews = 0
    profile.current_streak = 0
    profile.longest_streak = 0
    profile.last_activity_date = None

    db.commit()
    db.refresh(profile)
    return profile
