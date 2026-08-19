from datetime import datetime, timezone

from app.models import Profile, RecentMiss, UserWordProgress, WordPair
from app.security import hash_pin
from app.services import review_games
from app.services.review_games import MIXED_EVERY, RECOVERY_EVERY, SENTENCE_EVERY


def _profile(db_session, total_reviews: int = 0) -> Profile:
    p = Profile(
        slug="hebrew_learner", display_name="Hebrew Learner", native_lang="es", target_lang="he",
        pin_hash=hash_pin("1234"), total_reviews=total_reviews,
    )
    db_session.add(p)
    db_session.commit()
    return p


def _word(db_session, n: int, *, verified: bool = True) -> WordPair:
    w = WordPair(
        hebrew_word=f"מילה{n}", phonetic_en=f"mila{n}", phonetic_es=f"milá{n}",
        spanish_word=f"palabra{n}", english_word=f"word{n}", part_of_speech="noun",
        cefr_level="A1", topic="home", example_sentence_he="x", example_sentence_es="x",
        verified=verified,
    )
    db_session.add(w)
    db_session.commit()
    return w


def test_no_round_below_first_threshold(db_session):
    profile = _profile(db_session, total_reviews=RECOVERY_EVERY - 1)
    assert review_games.maybe_build_round(db_session, profile) is None


def test_no_round_at_zero(db_session):
    profile = _profile(db_session, total_reviews=0)
    assert review_games.maybe_build_round(db_session, profile) is None


def test_recovery_round_triggers_at_multiple_of_15(db_session):
    profile = _profile(db_session, total_reviews=RECOVERY_EVERY)
    word = _word(db_session, 1)
    db_session.add(RecentMiss(profile_id=profile.id, word_pair_id=word.id, missed_at=datetime.now(timezone.utc)))
    db_session.commit()

    round_out = review_games.maybe_build_round(db_session, profile)

    assert round_out is not None
    assert round_out.kind == "recovery"
    assert len(round_out.cards) == 1


def test_recovery_round_with_empty_miss_pool_returns_none(db_session):
    profile = _profile(db_session, total_reviews=RECOVERY_EVERY)
    assert review_games.maybe_build_round(db_session, profile) is None


def test_recovery_round_consumes_recent_misses(db_session):
    profile = _profile(db_session, total_reviews=RECOVERY_EVERY)
    word = _word(db_session, 1)
    db_session.add(RecentMiss(profile_id=profile.id, word_pair_id=word.id, missed_at=datetime.now(timezone.utc)))
    db_session.commit()

    review_games.maybe_build_round(db_session, profile)

    remaining = db_session.query(RecentMiss).filter_by(profile_id=profile.id).count()
    assert remaining == 0


def test_mixed_round_triggers_at_multiple_of_100(db_session):
    profile = _profile(db_session, total_reviews=MIXED_EVERY)
    word = _word(db_session, 1)
    db_session.add(
        UserWordProgress(profile_id=profile.id, word_pair_id=word.id, next_review_at=datetime.now(timezone.utc))
    )
    db_session.commit()

    round_out = review_games.maybe_build_round(db_session, profile)

    assert round_out is not None
    assert round_out.kind == "mixed"
    assert len(round_out.cards) == 1


def test_mixed_round_takes_priority_over_recovery_on_coincidence(db_session):
    # The LCM of RECOVERY_EVERY and MIXED_EVERY is a multiple of both — mixed must win.
    total = RECOVERY_EVERY * MIXED_EVERY // _gcd(RECOVERY_EVERY, MIXED_EVERY)  # least common multiple
    profile = _profile(db_session, total_reviews=total)
    word = _word(db_session, 1)
    db_session.add(RecentMiss(profile_id=profile.id, word_pair_id=word.id, missed_at=datetime.now(timezone.utc)))
    db_session.add(
        UserWordProgress(profile_id=profile.id, word_pair_id=word.id, next_review_at=datetime.now(timezone.utc))
    )
    db_session.commit()

    round_out = review_games.maybe_build_round(db_session, profile)

    assert round_out is not None
    assert round_out.kind == "mixed"
    # the miss must NOT have been consumed — recovery never ran
    assert db_session.query(RecentMiss).filter_by(profile_id=profile.id).count() == 1


def test_mixed_round_with_no_progress_rows_falls_through_to_none(db_session):
    profile = _profile(db_session, total_reviews=MIXED_EVERY)
    assert review_games.maybe_build_round(db_session, profile) is None


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def test_sentence_round_triggers_at_multiple_of_10(db_session):
    profile = _profile(db_session, total_reviews=SENTENCE_EVERY)
    word = _word(db_session, 1)
    db_session.add(
        UserWordProgress(
            profile_id=profile.id, word_pair_id=word.id, times_seen=1, next_review_at=datetime.now(timezone.utc)
        )
    )
    db_session.commit()

    round_out = review_games.maybe_build_round(db_session, profile)

    assert round_out is not None
    assert round_out.kind == "sentence"
    assert len(round_out.cards) == 1


def test_sentence_round_excludes_unseen_words(db_session):
    profile = _profile(db_session, total_reviews=SENTENCE_EVERY)
    word = _word(db_session, 1)
    db_session.add(
        UserWordProgress(
            profile_id=profile.id, word_pair_id=word.id, times_seen=0, next_review_at=datetime.now(timezone.utc)
        )
    )
    db_session.commit()

    assert review_games.maybe_build_round(db_session, profile) is None


def test_sentence_round_not_gated_by_exercise_level(db_session):
    # Level 0 (reveal) — well below the level-4 gate fill_blank normally
    # requires in the exercise ladder — must still be eligible here.
    profile = _profile(db_session, total_reviews=SENTENCE_EVERY)
    word = _word(db_session, 1)
    db_session.add(
        UserWordProgress(
            profile_id=profile.id,
            word_pair_id=word.id,
            times_seen=1,
            exercise_level=0,
            next_review_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    round_out = review_games.maybe_build_round(db_session, profile)

    assert round_out is not None
    assert round_out.kind == "sentence"


def test_mixed_wins_over_recovery_and_sentence_on_coincidence(db_session):
    # LCM of all three cadences is a multiple of all of them — mixed must win.
    total = SENTENCE_EVERY
    for every in (RECOVERY_EVERY, MIXED_EVERY):
        total = total * every // _gcd(total, every)
    profile = _profile(db_session, total_reviews=total)
    word = _word(db_session, 1)
    db_session.add(RecentMiss(profile_id=profile.id, word_pair_id=word.id, missed_at=datetime.now(timezone.utc)))
    db_session.add(
        UserWordProgress(
            profile_id=profile.id, word_pair_id=word.id, times_seen=1, next_review_at=datetime.now(timezone.utc)
        )
    )
    db_session.commit()

    round_out = review_games.maybe_build_round(db_session, profile)

    assert round_out is not None
    assert round_out.kind == "mixed"
    # neither recovery nor sentence ran
    assert db_session.query(RecentMiss).filter_by(profile_id=profile.id).count() == 1


def test_recovery_wins_over_sentence_on_coincidence(db_session, monkeypatch):
    # With the real constants, lcm(RECOVERY_EVERY, SENTENCE_EVERY) == 30 ==
    # MIXED_EVERY, so any review count that coincides for recovery+sentence
    # necessarily also coincides for mixed (see the test above) — there's no
    # real total_reviews value that isolates just recovery-vs-sentence.
    # Bump MIXED_EVERY out of the way so this collision is reachable, to
    # pin down the elif ordering (recovery before sentence) independently
    # of the mixed-wins-all-three case.
    monkeypatch.setattr(review_games, "MIXED_EVERY", 9973)  # large prime, won't coincide
    total = RECOVERY_EVERY * SENTENCE_EVERY // _gcd(RECOVERY_EVERY, SENTENCE_EVERY)
    profile = _profile(db_session, total_reviews=total)
    word = _word(db_session, 1)
    db_session.add(RecentMiss(profile_id=profile.id, word_pair_id=word.id, missed_at=datetime.now(timezone.utc)))
    db_session.add(
        UserWordProgress(
            profile_id=profile.id, word_pair_id=word.id, times_seen=1, next_review_at=datetime.now(timezone.utc)
        )
    )
    db_session.commit()

    round_out = review_games.maybe_build_round(db_session, profile)

    assert round_out is not None
    assert round_out.kind == "recovery"


def test_sentence_round_with_no_eligible_words_falls_through_to_none(db_session):
    profile = _profile(db_session, total_reviews=SENTENCE_EVERY)
    assert review_games.maybe_build_round(db_session, profile) is None
