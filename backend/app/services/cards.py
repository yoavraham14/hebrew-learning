"""Card selection and rating — the core study-flow logic (SPEC.md §4), plus
the exercise-ladder progression and review-game triggers layered on top
(see app.services.exercise_ladder / app.services.review_games).

Direction is entirely decided by `profile.target_lang`; nothing here is
hardcoded to "Hebrew learner" vs "Spanish learner" by name, so a future
third profile or a flipped direction is just a new Profile row.
"""

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyActivity, Profile, RecentMiss, UserWordProgress, WordPair
from app.schemas import AnswerResponse, CardResponse, RateResponse, RatingResult
from app.services import exercise_ladder, review_games
from app.services.review import compute_next_state
from app.services.streak import compute_streak_update


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_next_card(db: Session, profile: Profile) -> CardResponse | None:
    now = _utcnow()

    # 1. A due review, soonest first. Fluent words are excluded entirely —
    # they've graduated out of the normal deck (fluency feature — see
    # UserWordProgress.status); the mixed round is the only place they
    # still resurface, to periodically confirm they haven't been forgotten.
    due = db.scalar(
        select(UserWordProgress)
        .where(
            UserWordProgress.profile_id == profile.id,
            UserWordProgress.next_review_at <= now,
            UserWordProgress.status != "fluent",
        )
        .order_by(UserWordProgress.next_review_at.asc())
        .limit(1)
    )
    if due is not None:
        return exercise_ladder.build_card(db, profile, due.word_pair, level=due.exercise_level, is_review=True)

    # 2. A word this profile hasn't seen yet. Only verified words are ever
    # served as new material (SPEC.md-adjacent — see the translation-
    # verification feature; models.WordPair.verified docstring). Unverified
    # words just sit in the bank until a future verification sweep. Brand
    # new words always start at exercise_level 0 (reveal).
    seen_subquery = select(UserWordProgress.word_pair_id).where(
        UserWordProgress.profile_id == profile.id
    )
    new_word = db.scalar(
        select(WordPair)
        .where(WordPair.id.not_in(seen_subquery), WordPair.verified.is_(True))
        .order_by(WordPair.id.asc())
        .limit(1)
    )
    if new_word is not None:
        return exercise_ladder.build_card(db, profile, new_word, level=0, is_review=False)

    # 3. Bank exhausted for this profile (shouldn't normally happen — the
    # top-up job keeps unseen words above threshold) and nothing is due yet.
    # Fall back to the soonest upcoming review so the continuous deck never
    # dead-ends on a blank screen — still excluding fluent words; if
    # everything left is fluent, there's genuinely nothing left to serve in
    # the normal deck (return None below), which is correct, not a bug.
    upcoming = db.scalar(
        select(UserWordProgress)
        .where(UserWordProgress.profile_id == profile.id, UserWordProgress.status != "fluent")
        .order_by(UserWordProgress.next_review_at.asc())
        .limit(1)
    )
    if upcoming is not None:
        return exercise_ladder.build_card(
            db, profile, upcoming.word_pair, level=upcoming.exercise_level, is_review=True
        )

    return None


def _get_or_create_progress(db: Session, profile: Profile, word_pair_id: int, now: datetime) -> UserWordProgress:
    progress = db.scalar(
        select(UserWordProgress).where(
            UserWordProgress.profile_id == profile.id,
            UserWordProgress.word_pair_id == word_pair_id,
        )
    )
    if progress is None:
        progress = UserWordProgress(
            profile_id=profile.id,
            word_pair_id=word_pair_id,
            box=0,
            repetitions=0,
            ease_factor=2.5,
            interval_days=0,
            next_review_at=now,
            first_seen_at=now,
            times_seen=0,
            times_correct=0,
            status="new",
        )
        db.add(progress)
        db.flush()
    return progress


def _apply_result(
    db: Session, profile: Profile, progress: UserWordProgress, *, result: RatingResult, correct: bool, now: datetime
) -> None:
    """Shared tail end of rate_word/answer_word: box/interval ladder,
    exercise-level transition, streak/miss bookkeeping, total_reviews. The
    two entry points differ only in *how* `result`/`correct` are derived —
    self-rating for reveal cards, an objective answer check for MC cards.
    """
    ladder = compute_next_state(
        current_box=progress.box,
        current_repetitions=progress.repetitions,
        current_ease_factor=progress.ease_factor,
        result=result,
        now=now,
    )
    progress.box = ladder.box
    progress.repetitions = ladder.repetitions
    progress.ease_factor = ladder.ease_factor
    progress.interval_days = ladder.interval_days
    progress.next_review_at = ladder.next_review_at
    progress.last_result = result
    progress.times_seen += 1
    if correct:
        progress.times_correct += 1
    progress.last_seen_at = now
    if progress.first_seen_at is None:
        progress.first_seen_at = now

    transition = exercise_ladder.compute_level_transition(
        current_level=progress.exercise_level, current_streak=progress.exercise_level_streak, correct=correct
    )
    progress.exercise_level = transition.exercise_level
    progress.exercise_level_streak = transition.exercise_level_streak

    # Fluency status — recomputed from scratch on every rating, not a
    # one-way ratchet: a fluent word that gets missed (in a mixed round,
    # the only place it can still appear) has repetitions reset to 0 by
    # compute_next_state above, drops back to "learning" here, and
    # re-enters the normal deck automatically. That's the point of
    # periodically re-testing fluent words, not a bug.
    was_fluent = progress.status == "fluent"
    if progress.repetitions >= profile.fluency_threshold:
        progress.status = "fluent"
        if not was_fluent:
            progress.fluent_at = now
    else:
        progress.status = "learning"
        progress.fluent_at = None

    if not correct:
        db.add(RecentMiss(profile_id=profile.id, word_pair_id=progress.word_pair_id, missed_at=now))

    streak = compute_streak_update(
        last_activity_date=profile.last_activity_date,
        current_streak=profile.current_streak,
        today=now.date(),
    )
    profile.current_streak = streak.current_streak
    profile.last_activity_date = streak.last_activity_date
    profile.longest_streak = max(profile.longest_streak, streak.current_streak)
    profile.total_reviews += 1

    _record_daily_activity(db, profile, correct=correct, today=now.date())


def _record_daily_activity(db: Session, profile: Profile, *, correct: bool, today: date) -> None:
    """Upserts today's row — same find-or-create shape as
    _get_or_create_progress. Backs the progress page's daily-goal card and
    later feature-pass stages (activity calendar, weekly summary), which
    all read this same table rather than each keeping their own tally.
    """
    activity = db.scalar(
        select(DailyActivity).where(DailyActivity.profile_id == profile.id, DailyActivity.activity_date == today)
    )
    if activity is None:
        activity = DailyActivity(profile_id=profile.id, activity_date=today, review_count=0, correct_count=0)
        db.add(activity)
        db.flush()
    activity.review_count += 1
    if correct:
        activity.correct_count += 1


def rate_word(db: Session, profile: Profile, word_pair_id: int, result: RatingResult) -> RateResponse:
    """Self-rated path — level 0 (reveal) cards only."""
    now = _utcnow()
    progress = _get_or_create_progress(db, profile, word_pair_id, now)

    # `correct` mirrors review.LadderResult.correct: "knew_it" only. This is
    # also what drives exercise-level promotion for reveal cards — an
    # "almost" or "didnt_know" behaves like a miss for ladder purposes too.
    correct = result == "knew_it"
    _apply_result(db, profile, progress, result=result, correct=correct, now=now)

    round_due = review_games.maybe_build_round(db, profile)
    db.commit()

    return RateResponse(
        box=progress.box,
        next_review_at=progress.next_review_at,
        exercise_level=progress.exercise_level,
        round_due=round_due,
    )


def answer_word(db: Session, profile: Profile, word_pair_id: int, selected_word_pair_id: int) -> AnswerResponse:
    """Objectively-checked path — levels 1-4 (multiple_choice/reverse/
    audio_only/fill_blank) cards, and review-game round cards.
    """
    now = _utcnow()
    progress = _get_or_create_progress(db, profile, word_pair_id, now)

    # Capture the level the card was actually shown at *before* this
    # answer's transition mutates it — that's the language correct_text
    # needs to match (see exercise_ladder.correct_answer_text).
    level_at_answer = progress.exercise_level
    correct = selected_word_pair_id == word_pair_id
    result: RatingResult = "knew_it" if correct else "didnt_know"
    _apply_result(db, profile, progress, result=result, correct=correct, now=now)

    round_due = review_games.maybe_build_round(db, profile)

    correct_word_pair = db.get(WordPair, word_pair_id)
    correct_text = exercise_ladder.correct_answer_text(profile, correct_word_pair, level=level_at_answer)

    db.commit()

    return AnswerResponse(
        correct=correct,
        correct_word_pair_id=word_pair_id,
        correct_text=correct_text,
        box=progress.box,
        exercise_level=progress.exercise_level,
        round_due=round_due,
    )
