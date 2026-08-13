"""Stage E of the progress-page/study-flow feature pass: the activity
calendar and weekly summary. Both read DailyActivity — no new table.
"""

from datetime import datetime, timedelta, timezone

from app.models import DailyActivity, Profile, UserWordProgress, WordPair
from app.security import hash_pin
from app.services.progress import get_activity, get_weekly_summary


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


def _word(db_session, n: int = 0, **overrides) -> WordPair:
    data = dict(
        hebrew_word=f"מילה{n}", phonetic_en=f"mila{n}", phonetic_es=f"milá{n}",
        spanish_word=f"palabra{n}", english_word=f"word{n}", part_of_speech="noun",
        cefr_level="A1", topic="home", example_sentence_he="x", example_sentence_es="x",
        verified=True,
    )
    data.update(overrides)
    w = WordPair(**data)
    db_session.add(w)
    db_session.commit()
    return w


def _activity(db_session, profile: Profile, days_ago: int, review_count: int, correct_count: int) -> DailyActivity:
    # UTC "today", matching get_weekly_summary/get_activity's own
    # _utcnow().date() exactly — using local date.today() here can be off
    # by one near midnight depending on the machine's timezone.
    today_utc = datetime.now(timezone.utc).date()
    row = DailyActivity(
        profile_id=profile.id,
        activity_date=today_utc - timedelta(days=days_ago),
        review_count=review_count,
        correct_count=correct_count,
    )
    db_session.add(row)
    db_session.commit()
    return row


# ---------------------------------------------------------------------------
# get_activity
# ---------------------------------------------------------------------------


def test_get_activity_returns_rows_within_the_window(db_session):
    profile = _profile(db_session)
    _activity(db_session, profile, days_ago=0, review_count=5, correct_count=4)
    _activity(db_session, profile, days_ago=10, review_count=3, correct_count=3)

    rows = get_activity(db_session, profile, days=365)
    assert len(rows) == 2
    assert rows[0].activity_date <= rows[1].activity_date  # ascending order


def test_get_activity_excludes_rows_outside_the_window(db_session):
    profile = _profile(db_session)
    _activity(db_session, profile, days_ago=400, review_count=5, correct_count=4)

    rows = get_activity(db_session, profile, days=365)
    assert rows == []


def test_get_activity_never_seen_returns_empty_not_an_error(db_session):
    profile = _profile(db_session)
    assert get_activity(db_session, profile) == []


def test_get_activity_only_returns_this_profiles_rows(db_session):
    profile = _profile(db_session)
    other = _profile(db_session, slug="spanish_learner", native_lang="he", target_lang="es")
    _activity(db_session, other, days_ago=0, review_count=9, correct_count=9)

    assert get_activity(db_session, profile) == []


# ---------------------------------------------------------------------------
# get_weekly_summary
# ---------------------------------------------------------------------------


def test_weekly_summary_with_no_data_is_all_zero_not_an_error(db_session):
    profile = _profile(db_session)
    summary = get_weekly_summary(db_session, profile)
    assert summary.words_added == 0
    assert summary.words_became_fluent == 0
    assert summary.days_studied == 0
    assert summary.reviews_this_week == 0
    assert summary.accuracy_this_week == 0.0
    assert summary.accuracy_last_week == 0.0


def test_weekly_summary_counts_days_studied_and_reviews(db_session):
    profile = _profile(db_session)
    _activity(db_session, profile, days_ago=0, review_count=5, correct_count=4)
    _activity(db_session, profile, days_ago=2, review_count=3, correct_count=3)
    _activity(db_session, profile, days_ago=6, review_count=2, correct_count=1)  # edge of the 7-day window

    summary = get_weekly_summary(db_session, profile)
    assert summary.days_studied == 3
    assert summary.reviews_this_week == 10
    assert summary.accuracy_this_week == 80.0  # 8/10


def test_weekly_summary_excludes_data_older_than_7_days(db_session):
    profile = _profile(db_session)
    _activity(db_session, profile, days_ago=7, review_count=5, correct_count=5)  # just outside this week

    summary = get_weekly_summary(db_session, profile)
    assert summary.days_studied == 0
    assert summary.reviews_this_week == 0


def test_weekly_summary_accuracy_trend_compares_the_two_windows(db_session):
    profile = _profile(db_session)
    _activity(db_session, profile, days_ago=1, review_count=10, correct_count=9)  # this week: 90%
    _activity(db_session, profile, days_ago=10, review_count=10, correct_count=5)  # last week: 50%

    summary = get_weekly_summary(db_session, profile)
    assert summary.accuracy_this_week == 90.0
    assert summary.accuracy_last_week == 50.0


def test_weekly_summary_words_added_uses_first_seen_at(db_session):
    profile = _profile(db_session)
    recent_word = _word(db_session, 1)
    old_word = _word(db_session, 2)

    now = datetime.now(timezone.utc)
    db_session.add(
        UserWordProgress(profile_id=profile.id, word_pair_id=recent_word.id, first_seen_at=now, next_review_at=now)
    )
    db_session.add(
        UserWordProgress(
            profile_id=profile.id,
            word_pair_id=old_word.id,
            first_seen_at=now - timedelta(days=30),
            next_review_at=now,
        )
    )
    db_session.commit()

    summary = get_weekly_summary(db_session, profile)
    assert summary.words_added == 1


def test_weekly_summary_words_became_fluent_uses_fluent_at(db_session):
    profile = _profile(db_session)
    word = _word(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        UserWordProgress(
            profile_id=profile.id,
            word_pair_id=word.id,
            status="fluent",
            fluent_at=now,
            next_review_at=now,
        )
    )
    db_session.commit()

    summary = get_weekly_summary(db_session, profile)
    assert summary.words_became_fluent == 1
