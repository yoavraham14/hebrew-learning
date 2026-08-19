"""Standalone video library — NOT part of the study/exercise flow (see
app.services.cards / app.services.exercise_ladder for that). Videos are a
shared catalog (app.models.Video, seeded once via app.scripts.seed_videos)
watched per-profile (app.models.WatchedVideo).
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, Video, WatchedVideo
from app.schemas import VideoOut


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_video_out(video: Video, *, watched: bool) -> VideoOut:
    return VideoOut(
        id=video.id,
        title=video.title,
        youtube_video_id=video.youtube_video_id,
        level=video.level,
        topic=video.topic,
        ordering=video.ordering,
        watched=watched,
    )


def list_videos(db: Session, profile: Profile) -> list[VideoOut]:
    """Every catalog video, ordered by the source list's own ordering, with
    per-profile watch state joined in — one round trip, no separate
    "am I watching this" call needed by the frontend.
    """
    videos = db.scalars(select(Video).order_by(Video.ordering.asc())).all()
    watched_ids = set(
        db.scalars(select(WatchedVideo.video_id).where(WatchedVideo.profile_id == profile.id)).all()
    )
    return [_to_video_out(v, watched=v.id in watched_ids) for v in videos]


def _get_video_or_404(db: Session, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="video not found")
    return video


def mark_watched(db: Session, profile: Profile, video_id: int) -> VideoOut:
    """Called once the YouTube IFrame API fires ENDED for this video (see
    the video-library plan) — idempotent: watching a video a second time
    doesn't duplicate the row or move watched_at, same "first-time
    achievement" spirit as WatchedVideo's docstring.
    """
    video = _get_video_or_404(db, video_id)

    existing = db.scalar(
        select(WatchedVideo).where(WatchedVideo.profile_id == profile.id, WatchedVideo.video_id == video_id)
    )
    if existing is None:
        db.add(WatchedVideo(profile_id=profile.id, video_id=video_id, watched_at=_utcnow()))
        db.commit()

    return _to_video_out(video, watched=True)
