"""Pure review-interval-ladder logic (SPEC.md §4.1).

Kept side-effect-free and DB-free on purpose: it's the piece most worth
unit-testing in isolation, and the schema (`repetitions`, `ease_factor`)
already carries the fields a future SM-2 implementation would need — only
this function would need to change, not the model or the API.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.schemas import RatingResult

# Days-to-wait once a word reaches box N via consecutive "knew it" ratings.
# Box advances by exactly one step per "knew it"; index 0 is the first step
# up from a brand-new or just-reset word.
LADDER_DAYS: list[float] = [1, 3, 7, 14, 30, 60, 120]

DIDNT_KNOW_RESURFACE_MINUTES = 10
ALMOST_INTERVAL_DAYS = 1.0

# A word counts as "known" for the progress view once it has reached this
# box (i.e. survived enough consecutive correct reviews to be on a >=7-day
# interval). Used by app.services.progress.
KNOWN_BOX_THRESHOLD = 2


@dataclass(frozen=True)
class LadderResult:
    box: int
    repetitions: int
    ease_factor: float
    interval_days: float
    next_review_at: datetime
    correct: bool


def compute_next_state(
    *,
    current_box: int,
    current_repetitions: int,
    current_ease_factor: float,
    result: RatingResult,
    now: datetime,
) -> LadderResult:
    if result == "didnt_know":
        return LadderResult(
            box=0,
            repetitions=0,
            ease_factor=max(1.3, current_ease_factor - 0.2),
            interval_days=0.0,
            next_review_at=now + timedelta(minutes=DIDNT_KNOW_RESURFACE_MINUTES),
            correct=False,
        )

    if result == "almost":
        return LadderResult(
            box=current_box,
            repetitions=current_repetitions,
            ease_factor=current_ease_factor,
            interval_days=ALMOST_INTERVAL_DAYS,
            next_review_at=now + timedelta(days=ALMOST_INTERVAL_DAYS),
            correct=False,
        )

    if result == "knew_it":
        box = min(current_box + 1, len(LADDER_DAYS) - 1)
        interval_days = LADDER_DAYS[box]
        return LadderResult(
            box=box,
            repetitions=current_repetitions + 1,
            ease_factor=min(3.0, current_ease_factor + 0.1),
            interval_days=interval_days,
            next_review_at=now + timedelta(days=interval_days),
            correct=True,
        )

    raise ValueError(f"unknown rating result: {result!r}")


def is_known(box: int) -> bool:
    return box >= KNOWN_BOX_THRESHOLD
