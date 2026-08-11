from datetime import datetime, timedelta, timezone

from app.services.review import (
    ALMOST_INTERVAL_DAYS,
    DIDNT_KNOW_RESURFACE_MINUTES,
    KNOWN_BOX_THRESHOLD,
    LADDER_DAYS,
    compute_next_state,
    is_known,
)

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_knew_it_advances_box_and_sets_ladder_interval():
    result = compute_next_state(
        current_box=0, current_repetitions=0, current_ease_factor=2.5, result="knew_it", now=NOW
    )
    assert result.box == 1
    assert result.repetitions == 1
    assert result.correct is True
    assert result.interval_days == LADDER_DAYS[1]
    assert result.next_review_at == NOW + timedelta(days=LADDER_DAYS[1])


def test_knew_it_repeated_keeps_advancing():
    state = compute_next_state(
        current_box=0, current_repetitions=0, current_ease_factor=2.5, result="knew_it", now=NOW
    )
    state2 = compute_next_state(
        current_box=state.box,
        current_repetitions=state.repetitions,
        current_ease_factor=state.ease_factor,
        result="knew_it",
        now=NOW,
    )
    assert state2.box == 2
    assert state2.repetitions == 2
    assert state2.interval_days == LADDER_DAYS[2]


def test_knew_it_caps_at_top_of_ladder():
    top = len(LADDER_DAYS) - 1
    result = compute_next_state(
        current_box=top, current_repetitions=10, current_ease_factor=2.5, result="knew_it", now=NOW
    )
    assert result.box == top  # doesn't overflow past the ladder
    assert result.interval_days == LADDER_DAYS[top]


def test_almost_keeps_box_and_uses_short_interval():
    result = compute_next_state(
        current_box=3, current_repetitions=3, current_ease_factor=2.5, result="almost", now=NOW
    )
    assert result.box == 3  # unchanged
    assert result.repetitions == 3  # unchanged
    assert result.correct is False
    assert result.interval_days == ALMOST_INTERVAL_DAYS
    assert result.next_review_at == NOW + timedelta(days=ALMOST_INTERVAL_DAYS)


def test_didnt_know_resets_box_and_resurfaces_soon():
    result = compute_next_state(
        current_box=4, current_repetitions=4, current_ease_factor=2.7, result="didnt_know", now=NOW
    )
    assert result.box == 0
    assert result.repetitions == 0
    assert result.correct is False
    assert result.next_review_at == NOW + timedelta(minutes=DIDNT_KNOW_RESURFACE_MINUTES)
    # ease factor drops but never below the floor
    assert result.ease_factor == 2.5


def test_didnt_know_ease_factor_floor():
    result = compute_next_state(
        current_box=1, current_repetitions=1, current_ease_factor=1.35, result="didnt_know", now=NOW
    )
    assert result.ease_factor >= 1.3


def test_unknown_result_raises():
    import pytest

    with pytest.raises(ValueError):
        compute_next_state(
            current_box=0,
            current_repetitions=0,
            current_ease_factor=2.5,
            result="maybe",  # type: ignore[arg-type]
            now=NOW,
        )


def test_is_known_threshold():
    assert is_known(KNOWN_BOX_THRESHOLD) is True
    assert is_known(KNOWN_BOX_THRESHOLD - 1) is False
    assert is_known(0) is (KNOWN_BOX_THRESHOLD == 0)
