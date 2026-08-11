"""Card selection and rating — the core study-flow logic (SPEC.md §4).

Direction is entirely decided by `profile.target_lang`; nothing here is
hardcoded to "Hebrew learner" vs "Spanish learner" by name, so a future
third profile or a flipped direction is just a new Profile row.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Profile, UserWordProgress, WordPair
from app.schemas import CardOut, RateResponse, RatingResult
from app.services.review import compute_next_state
from app.services.streak import compute_streak_update


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_card_out(profile: Profile, word_pair: WordPair, *, is_review: bool) -> CardOut:
    if profile.target_lang == "he":
        # Hebrew learner: native Spanish, target Hebrew.
        return CardOut(
            word_pair_id=word_pair.id,
            prompt=word_pair.spanish_word,
            prompt_lang="es",
            reveal_english=word_pair.english_word,
            reveal_target_word=word_pair.hebrew_word,
            reveal_target_lang="he",
            reveal_phonetic=word_pair.phonetic_es,
            example_target=word_pair.example_sentence_he,
            example_native=word_pair.example_sentence_es,
            part_of_speech=word_pair.part_of_speech,
            cefr_level=word_pair.cefr_level,
            topic=word_pair.topic,
            is_review=is_review,
        )

    # Spanish learner: native Hebrew, target Spanish. No special phonetic
    # needed — Spanish uses the Latin alphabet, which the learner already
    # reads fluently as a second/foreign script.
    return CardOut(
        word_pair_id=word_pair.id,
        prompt=word_pair.hebrew_word,
        prompt_lang="he",
        reveal_english=word_pair.english_word,
        reveal_target_word=word_pair.spanish_word,
        reveal_target_lang="es",
        reveal_phonetic=None,
        example_target=word_pair.example_sentence_es,
        example_native=word_pair.example_sentence_he,
        part_of_speech=word_pair.part_of_speech,
        cefr_level=word_pair.cefr_level,
        topic=word_pair.topic,
        is_review=is_review,
    )


def get_next_card(db: Session, profile: Profile) -> CardOut | None:
    now = _utcnow()

    # 1. A due review, soonest first.
    due = db.scalar(
        select(UserWordProgress)
        .where(
            UserWordProgress.profile_id == profile.id,
            UserWordProgress.next_review_at <= now,
        )
        .order_by(UserWordProgress.next_review_at.asc())
        .limit(1)
    )
    if due is not None:
        return _to_card_out(profile, due.word_pair, is_review=True)

    # 2. A word this profile hasn't seen yet.
    seen_subquery = select(UserWordProgress.word_pair_id).where(
        UserWordProgress.profile_id == profile.id
    )
    new_word = db.scalar(
        select(WordPair).where(WordPair.id.not_in(seen_subquery)).order_by(WordPair.id.asc()).limit(1)
    )
    if new_word is not None:
        return _to_card_out(profile, new_word, is_review=False)

    # 3. Bank exhausted for this profile (shouldn't normally happen — the
    # top-up job keeps unseen words above threshold) and nothing is due yet.
    # Fall back to the soonest upcoming review so the continuous deck never
    # dead-ends on a blank screen.
    upcoming = db.scalar(
        select(UserWordProgress)
        .where(UserWordProgress.profile_id == profile.id)
        .order_by(UserWordProgress.next_review_at.asc())
        .limit(1)
    )
    if upcoming is not None:
        return _to_card_out(profile, upcoming.word_pair, is_review=True)

    return None


def rate_word(db: Session, profile: Profile, word_pair_id: int, result: RatingResult) -> RateResponse:
    now = _utcnow()

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
        )
        db.add(progress)

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
    if ladder.correct:
        progress.times_correct += 1
    progress.last_seen_at = now
    if progress.first_seen_at is None:
        progress.first_seen_at = now

    streak = compute_streak_update(
        last_activity_date=profile.last_activity_date,
        current_streak=profile.current_streak,
        today=now.date(),
    )
    profile.current_streak = streak.current_streak
    profile.last_activity_date = streak.last_activity_date

    db.commit()

    return RateResponse(box=progress.box, next_review_at=progress.next_review_at)
