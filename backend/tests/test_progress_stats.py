"""Stage C of the progress-page/study-flow feature pass: the richer
GET /api/progress payload (fluent count, streak+longest, due-today,
daily-goal-vs-today) and the daily_activity upsert that backs it.
"""

from datetime import date, datetime, timedelta, timezone

from app.models import DailyActivity, Profile, UserWordProgress, Video, WatchedVideo, WordPair
from app.security import hash_pin
from app.services.cards import answer_word, rate_word
from app.services.progress import get_progress


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


def test_daily_activity_upserted_and_incremented_within_the_same_day(db_session):
    profile = _profile(db_session)
    word1 = _word(db_session, 1)
    word2 = _word(db_session, 2)

    rate_word(db_session, profile, word1.id, "knew_it")
    rate_word(db_session, profile, word2.id, "didnt_know")

    rows = db_session.query(DailyActivity).filter_by(profile_id=profile.id).all()
    assert len(rows) == 1  # same calendar day -> one row, not two
    assert rows[0].activity_date == datetime.now(timezone.utc).date()
    assert rows[0].review_count == 2
    assert rows[0].correct_count == 1  # only the "knew_it" one


def test_answer_word_also_records_daily_activity(db_session):
    profile = _profile(db_session)
    word = _word(db_session)

    answer_word(db_session, profile, word.id, word.id)  # correct

    row = db_session.query(DailyActivity).filter_by(profile_id=profile.id).one()
    assert row.review_count == 1
    assert row.correct_count == 1


def test_longest_streak_tracks_the_max_and_never_shrinks(db_session):
    profile = _profile(db_session)
    word = _word(db_session)

    rate_word(db_session, profile, word.id, "knew_it")
    assert profile.current_streak == 1
    assert profile.longest_streak == 1

    # Simulate the streak having been higher before, then dropping (a gap
    # broke it) — longest_streak must not follow it back down.
    profile.longest_streak = 10
    profile.current_streak = 1
    profile.last_activity_date = date.today() - timedelta(days=5)
    db_session.commit()

    rate_word(db_session, profile, word.id, "knew_it")  # gap -> streak restarts at 1
    assert profile.current_streak == 1
    assert profile.longest_streak == 10  # untouched, still the max ever seen


def test_get_progress_reports_fluent_count_and_bank_total(db_session):
    profile = _profile(db_session, fluency_threshold=1)
    fluent_word = _word(db_session, 1)
    learning_word = _word(db_session, 2)
    _word(db_session, 3, verified=False)  # unverified — must not count toward the bank total

    rate_word(db_session, profile, fluent_word.id, "knew_it")  # -> fluent immediately (threshold=1)
    rate_word(db_session, profile, learning_word.id, "didnt_know")

    progress = get_progress(db_session, profile)
    assert progress.words_seen == 2
    assert progress.words_fluent == 1
    assert progress.total_verified_words == 2  # the two verified words, not the unverified one


def test_get_progress_due_today_excludes_fluent_words(db_session):
    profile = _profile(db_session, fluency_threshold=1)
    word = _word(db_session)

    rate_word(db_session, profile, word.id, "knew_it")  # -> fluent
    progress_row = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    progress_row.next_review_at = datetime.now(timezone.utc)  # force "due" if it weren't fluent
    db_session.commit()

    progress = get_progress(db_session, profile)
    assert progress.due_today == 0  # fluent — excluded, matches get_next_card's own filter


def test_get_progress_today_review_count_reflects_daily_activity(db_session):
    profile = _profile(db_session)
    word = _word(db_session)

    assert get_progress(db_session, profile).today_review_count == 0

    rate_word(db_session, profile, word.id, "knew_it")
    assert get_progress(db_session, profile).today_review_count == 1


def test_get_progress_surfaces_daily_goal(db_session):
    profile = _profile(db_session, daily_goal=25)
    progress = get_progress(db_session, profile)
    assert progress.daily_goal == 25


# ---------------------------------------------------------------------------
# Video-library stats (videos_watched / videos_watched_this_week /
# weekly_video_goal) — see app.models.WatchedVideo / app.services.videos.
# ---------------------------------------------------------------------------


def _video(db_session, n: int) -> Video:
    v = Video(title=f"Video {n}", youtube_video_id=f"vid{n:06d}", level="A1", topic="test", ordering=n)
    db_session.add(v)
    db_session.commit()
    return v


def test_get_progress_surfaces_weekly_video_goal(db_session):
    profile = _profile(db_session, weekly_video_goal=3)
    progress = get_progress(db_session, profile)
    assert progress.weekly_video_goal == 3


def test_get_progress_counts_watched_videos(db_session):
    profile = _profile(db_session)
    video1 = _video(db_session, 1)
    video2 = _video(db_session, 2)
    now = datetime.now(timezone.utc)
    db_session.add(WatchedVideo(profile_id=profile.id, video_id=video1.id, watched_at=now))
    db_session.add(WatchedVideo(profile_id=profile.id, video_id=video2.id, watched_at=now))
    db_session.commit()

    progress = get_progress(db_session, profile)
    assert progress.videos_watched == 2
    assert progress.videos_watched_this_week == 2


def test_get_progress_videos_watched_this_week_excludes_older_watches(db_session):
    profile = _profile(db_session)
    video1 = _video(db_session, 1)
    video2 = _video(db_session, 2)
    now = datetime.now(timezone.utc)
    db_session.add(WatchedVideo(profile_id=profile.id, video_id=video1.id, watched_at=now))
    db_session.add(
        WatchedVideo(profile_id=profile.id, video_id=video2.id, watched_at=now - timedelta(days=10))
    )
    db_session.commit()

    progress = get_progress(db_session, profile)
    assert progress.videos_watched == 2  # lifetime total includes both
    assert progress.videos_watched_this_week == 1  # only the recent one


def test_get_progress_video_stats_zero_when_none_watched(db_session):
    profile = _profile(db_session)
    progress = get_progress(db_session, profile)
    assert progress.videos_watched == 0
    assert progress.videos_watched_this_week == 0
