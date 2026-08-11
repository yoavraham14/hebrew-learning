from fastapi import APIRouter

from app.deps import CurrentProfile, DbSession
from app.schemas import ProgressOut
from app.services.progress import get_progress

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("", response_model=ProgressOut)
def progress(profile: CurrentProfile, db: DbSession) -> ProgressOut:
    return get_progress(db, profile)
