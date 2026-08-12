from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentProfile, DbSession
from app.models import Profile
from app.schemas import ProfilePublicOut, UpdateProfileSettingsRequest

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
