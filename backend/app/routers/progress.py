from fastapi import APIRouter

from app.deps import CurrentProfile, DbSession
from app.schemas import ActivityDayOut, ProgressOut, SetStarredRequest, WeeklySummaryOut, WordProgressOut
from app.services.progress import (
    get_activity,
    get_progress,
    get_weekly_summary,
    list_word_progress,
    mark_fluent,
    reset_word,
    set_starred,
)

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("", response_model=ProgressOut)
def progress(profile: CurrentProfile, db: DbSession) -> ProgressOut:
    return get_progress(db, profile)


@router.get("/words", response_model=list[WordProgressOut])
def words(profile: CurrentProfile, db: DbSession) -> list[WordProgressOut]:
    return list_word_progress(db, profile)


@router.post("/words/{word_pair_id}/mark-fluent", response_model=WordProgressOut)
def mark_word_fluent(word_pair_id: int, profile: CurrentProfile, db: DbSession) -> WordProgressOut:
    return mark_fluent(db, profile, word_pair_id)


@router.post("/words/{word_pair_id}/reset", response_model=WordProgressOut)
def reset_word_progress(word_pair_id: int, profile: CurrentProfile, db: DbSession) -> WordProgressOut:
    return reset_word(db, profile, word_pair_id)


@router.post("/words/{word_pair_id}/star", response_model=WordProgressOut)
def star_word(
    word_pair_id: int, payload: SetStarredRequest, profile: CurrentProfile, db: DbSession
) -> WordProgressOut:
    return set_starred(db, profile, word_pair_id, payload.starred)


@router.get("/activity", response_model=list[ActivityDayOut])
def activity(profile: CurrentProfile, db: DbSession) -> list[ActivityDayOut]:
    return get_activity(db, profile)


@router.get("/weekly-summary", response_model=WeeklySummaryOut)
def weekly_summary(profile: CurrentProfile, db: DbSession) -> WeeklySummaryOut:
    return get_weekly_summary(db, profile)
