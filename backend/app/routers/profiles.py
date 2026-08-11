from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DbSession
from app.models import Profile
from app.schemas import ProfilePublicOut

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfilePublicOut])
def list_profiles(db: DbSession) -> list[Profile]:
    """Public — used by the profile picker before login. Deliberately
    excludes pin_hash (ProfilePublicOut doesn't have the field at all).
    """
    return list(db.scalars(select(Profile).order_by(Profile.id)))
