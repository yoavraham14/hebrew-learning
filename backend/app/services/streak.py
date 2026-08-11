"""Pure daily-streak logic, kept separate and DB-free for the same reason as
review.py — easy to unit test, easy to reason about.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class StreakUpdate:
    current_streak: int
    last_activity_date: date


def compute_streak_update(
    *, last_activity_date: date | None, current_streak: int, today: date
) -> StreakUpdate:
    if last_activity_date == today:
        # Already counted today — no change.
        return StreakUpdate(current_streak=current_streak, last_activity_date=today)

    if last_activity_date is not None and (today - last_activity_date).days == 1:
        return StreakUpdate(current_streak=current_streak + 1, last_activity_date=today)

    # First-ever activity, or a gap of more than one day: streak restarts.
    return StreakUpdate(current_streak=1, last_activity_date=today)
