"""Standalone video library — app.services.videos / app.routers.videos.
Not part of the study/exercise flow (see app.services.cards for that).
"""

import pytest
from fastapi import HTTPException

from app.models import Profile, Video, WatchedVideo
from app.security import hash_pin
from app.services.videos import list_videos, mark_watched


def _profile(db_session, **overrides) -> Profile:
    data = dict(
        slug="hebrew_learner", display_name="Hebrew Learner", native_lang="es", target_lang="he",
        pin_hash=hash_pin("1234"),
    )
    data.update(overrides)
    p = Profile(**data)
    db_session.add(p)
    db_session.commit()
    return p


def _video(db_session, n: int, **overrides) -> Video:
    data = dict(title=f"Video {n}", youtube_video_id=f"vid{n:06d}", level="A1", topic="test", ordering=n)
    data.update(overrides)
    v = Video(**data)
    db_session.add(v)
    db_session.commit()
    return v


def _login(client, slug: str, pin: str) -> dict:
    resp = client.post("/api/auth/login", json={"profile_slug": slug, "pin": pin})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# list_videos
# ---------------------------------------------------------------------------


def test_list_videos_ordered_by_ordering(db_session):
    profile = _profile(db_session)
    _video(db_session, 1, ordering=30)
    _video(db_session, 2, ordering=10)
    _video(db_session, 3, ordering=20)

    videos = list_videos(db_session, profile)

    assert [v.ordering for v in videos] == [10, 20, 30]


def test_list_videos_reports_watched_state_per_profile(db_session):
    watcher = _profile(db_session)
    other = _profile(db_session, slug="spanish_learner", native_lang="he", target_lang="es")
    video = _video(db_session, 1)

    mark_watched(db_session, watcher, video.id)

    watcher_videos = list_videos(db_session, watcher)
    other_videos = list_videos(db_session, other)

    assert watcher_videos[0].watched is True
    assert other_videos[0].watched is False  # watch state must not leak across profiles


def test_list_videos_empty_catalog_returns_empty_list(db_session):
    profile = _profile(db_session)
    assert list_videos(db_session, profile) == []


# ---------------------------------------------------------------------------
# mark_watched
# ---------------------------------------------------------------------------


def test_mark_watched_creates_a_row(db_session):
    profile = _profile(db_session)
    video = _video(db_session, 1)

    result = mark_watched(db_session, profile, video.id)

    assert result.watched is True
    row = db_session.query(WatchedVideo).filter_by(profile_id=profile.id, video_id=video.id).one()
    assert row.watched_at is not None


def test_mark_watched_is_idempotent(db_session):
    profile = _profile(db_session)
    video = _video(db_session, 1)

    mark_watched(db_session, profile, video.id)
    first_watched_at = db_session.query(WatchedVideo).filter_by(profile_id=profile.id).one().watched_at
    mark_watched(db_session, profile, video.id)  # second ENDED event for the same video

    rows = db_session.query(WatchedVideo).filter_by(profile_id=profile.id, video_id=video.id).all()
    assert len(rows) == 1  # not duplicated
    assert rows[0].watched_at == first_watched_at  # not moved forward either


def test_mark_watched_unknown_video_404s(db_session):
    profile = _profile(db_session)
    with pytest.raises(HTTPException) as exc_info:
        mark_watched(db_session, profile, 999999)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# API layer
# ---------------------------------------------------------------------------


def test_list_videos_endpoint_requires_auth(client, db_session):
    _profile(db_session)
    resp = client.get("/api/videos")
    assert resp.status_code == 401


def test_list_videos_endpoint_full_flow(client, db_session):
    _profile(db_session)
    _video(db_session, 1)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.get("/api/videos", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["watched"] is False


def test_watch_endpoint_marks_watched(client, db_session):
    _profile(db_session)
    video = _video(db_session, 1)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.post(f"/api/videos/{video.id}/watch", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["watched"] is True

    # Reflected on the next list call too.
    resp = client.get("/api/videos", headers=headers)
    assert resp.json()[0]["watched"] is True


def test_watch_endpoint_unknown_video_404s(client, db_session):
    _profile(db_session)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.post("/api/videos/999999/watch", headers=headers)
    assert resp.status_code == 404
