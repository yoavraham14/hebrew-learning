"""Three review-game triggers layered on the continuous deck — SPEC.md-adjacent
(see the review-games plan). All keyed off Profile.total_reviews, which the
caller (app.services.cards) increments on every rate/answer call regardless
of exercise type.

- Recovery round: every RECOVERY_EVERY-th review, drawn from this profile's
  RecentMiss rows (its most recent wrong answers), consumed (deleted) once
  served — a miss is only ever offered in one recovery round.
- Mixed round: every MIXED_EVERY-th review, a broader refresher drawn from
  due/near-due words across the whole deck — not itself scoped to misses,
  and nothing is consumed. Also the only place a fluent word (§ progress
  feature pass — see UserWordProgress.status) can resurface once it's
  graduated out of the normal deck; the query here was never filtered by
  status, so that falls out for free.
- Sentence round: every SENTENCE_EVERY-th review, fill-in-the-blank cards
  (exercise_ladder's "fill_blank" mechanic, normally reserved for words at
  exercise_level 4) drawn from ANY word this profile has seen at least once
  (UserWordProgress.times_seen >= 1) — deliberately NOT gated by the word's
  own exercise_level, since this round is meant as a teaching tool woven
  into regular practice rather than a reward for already-mastered words.
  Nothing is consumed.
- Priority when multiple cadences land on the same review (e.g. #30 hits
  both MIXED_EVERY and SENTENCE_EVERY): mixed > recovery > sentence. The
  rarer/broader round wins; a deferred sentence round just fires again at
  its own next multiple of ten, so nothing is lost, only delayed.

Rounds are delivered as a side-channel (`round_due`) on the RateResponse/
AnswerResponse of the review that triggered them, not as a separate
endpoint — see schemas.RoundOut. Recovery/mixed round cards are always plain
"multiple_choice" regardless of the word's own stored exercise_level;
sentence round cards are always "fill_blank". All are supplementary
practice, not level-progression cards, and are answered through the same
POST /api/cards/{id}/answer endpoint as any other card.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Profile, RecentMiss, UserWordProgress
from app.schemas import RoundOut
from app.services import exercise_ladder

RECOVERY_EVERY = 15
RECOVERY_ROUND_SIZE = 5
MIXED_EVERY = 30
MIXED_ROUND_SIZE = 8
SENTENCE_EVERY = 10
SENTENCE_ROUND_SIZE = 5


def _build_recovery_round(db: Session, profile: Profile) -> list:
    misses = db.scalars(
        select(RecentMiss)
        .where(RecentMiss.profile_id == profile.id)
        .order_by(RecentMiss.missed_at.desc())
        .limit(RECOVERY_ROUND_SIZE)
    ).all()
    if not misses:
        return []
    cards = [
        exercise_ladder.build_multiple_choice_card(
            db, profile, miss.word_pair, exercise_type="multiple_choice", is_review=True
        )
        for miss in misses
    ]
    for miss in misses:
        db.delete(miss)
    db.flush()
    return cards


def _build_mixed_round(db: Session, profile: Profile) -> list:
    rows = db.scalars(
        select(UserWordProgress)
        .where(UserWordProgress.profile_id == profile.id)
        .order_by(UserWordProgress.next_review_at.asc())
        .limit(MIXED_ROUND_SIZE)
    ).all()
    if not rows:
        return []
    return [
        exercise_ladder.build_multiple_choice_card(
            db, profile, row.word_pair, exercise_type="multiple_choice", is_review=True
        )
        for row in rows
    ]


def _build_sentence_round(db: Session, profile: Profile) -> list:
    rows = db.scalars(
        select(UserWordProgress)
        .where(UserWordProgress.profile_id == profile.id, UserWordProgress.times_seen >= 1)
        .order_by(func.random())
        .limit(SENTENCE_ROUND_SIZE)
    ).all()
    if not rows:
        return []
    return [
        exercise_ladder.build_multiple_choice_card(
            db, profile, row.word_pair, exercise_type="fill_blank", is_review=True
        )
        for row in rows
    ]


def maybe_build_round(db: Session, profile: Profile) -> RoundOut | None:
    if profile.total_reviews <= 0:
        return None

    if profile.total_reviews % MIXED_EVERY == 0:
        cards = _build_mixed_round(db, profile)
        return RoundOut(kind="mixed", cards=cards) if cards else None

    if profile.total_reviews % RECOVERY_EVERY == 0:
        cards = _build_recovery_round(db, profile)
        return RoundOut(kind="recovery", cards=cards) if cards else None

    if profile.total_reviews % SENTENCE_EVERY == 0:
        cards = _build_sentence_round(db, profile)
        return RoundOut(kind="sentence", cards=cards) if cards else None

    return None
