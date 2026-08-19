from fastapi import APIRouter

from app.deps import CurrentProfile, DbSession
from app.schemas import VideoOut
from app.services.videos import list_videos, mark_watched

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.get("", response_model=list[VideoOut])
def videos(profile: CurrentProfile, db: DbSession) -> list[VideoOut]:
    return list_videos(db, profile)


@router.post("/{video_id}/watch", response_model=VideoOut)
def watch_video(video_id: int, profile: CurrentProfile, db: DbSession) -> VideoOut:
    return mark_watched(db, profile, video_id)
