from fastapi import APIRouter, status
from sqlalchemy import select

from app.deps import CurrentProfile, DbSession
from app.models import Profile
from app.schemas import CreateProfileRequest, ProfilePublicOut, ResetProfileRequest, UpdateProfileSettingsRequest
from app.services.profiles import create_profile, reset_profile

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfilePublicOut])
def list_profiles(db: DbSession) -> list[Profile]:
    """Public — used by the profile picker before login. Deliberately
    excludes pin_hash (ProfilePublicOut doesn't have the field at all).
    """
    return list(db.scalars(select(Profile).order_by(Profile.id)))


@router.patch("/me", response_model=ProfilePublicOut)
def update_my_settings(payload: UpdateProfileSettingsRequest, profile: CurrentProfile, db: DbSession) -> Profile:
    """Editable at any time, not just at first login — e.g. raising your
    fluency threshold doesn't retroactively downgrade already-fluent words
    (see UserWordProgress.status's docstring); it only changes the bar for
    words that haven't crossed it yet.
    """
    if payload.fluency_threshold is not None:
        profile.fluency_threshold = payload.fluency_threshold
    if payload.daily_goal is not None:
        profile.daily_goal = payload.daily_goal
    db.commit()
    db.refresh(profile)
    return profile


@router.post("", response_model=ProfilePublicOut, status_code=status.HTTP_201_CREATED)
def add_profile(payload: CreateProfileRequest, profile: CurrentProfile, db: DbSession) -> Profile:
    """Self-service profile creation — requires an existing authenticated
    session (the `profile: CurrentProfile` dependency is unused beyond
    that auth check). Softens SPEC.md §3's "no public signup" to "not
    reachable without already having access" rather than reopening it to
    the whole internet — see services/profiles.py's docstring.
    """
    return create_profile(db, display_name=payload.display_name, pin=payload.pin, direction=payload.direction)


@router.post("/{slug}/reset", response_model=ProfilePublicOut)
def reset_profile_progress(
    slug: str, payload: ResetProfileRequest, profile: CurrentProfile, db: DbSession
) -> Profile:
    """Irreversible — wipes all progress for the profile at `slug` (which
    may or may not be the caller's own profile; this is gated by the
    shared RESET_PASSWORD, an operator-level secret, not by the caller's
    own identity). See services/profiles.reset_profile for exactly what's
    deleted vs. preserved.
    """
    return reset_profile(db, target_slug=slug, password=payload.password, confirmation=payload.confirmation)
