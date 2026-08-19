"""Stage B of the progress-page/study-flow feature pass: user-configurable
fluency threshold, and fluent words leaving the normal deck (still eligible
for the mixed round). See app.services.cards._apply_result / get_next_card.
"""

from datetime import datetime, timezone

from app.models import Profile, UserWordProgress, WordPair
from app.security import hash_pin
from app.services.cards import answer_word, get_next_card, rate_word


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


# ---------------------------------------------------------------------------
# PATCH /api/profiles/me
# ---------------------------------------------------------------------------


def _login(client, slug: str, pin: str) -> dict:
    resp = client.post("/api/auth/login", json={"profile_slug": slug, "pin": pin})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_update_fluency_threshold(client, db_session):
    _profile(db_session)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.patch("/api/profiles/me", json={"fluency_threshold": 5}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["fluency_threshold"] == 5


def test_update_weekly_video_goal(client, db_session):
    _profile(db_session)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.patch("/api/profiles/me", json={"weekly_video_goal": 3}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["weekly_video_goal"] == 3


def test_omitting_weekly_video_goal_leaves_it_unchanged(client, db_session):
    _profile(db_session, weekly_video_goal=4)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.patch("/api/profiles/me", json={}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["weekly_video_goal"] == 4


def test_update_fluency_threshold_requires_auth(client, db_session):
    _profile(db_session)
    resp = client.patch("/api/profiles/me", json={"fluency_threshold": 5})
    assert resp.status_code == 401


def test_update_fluency_threshold_rejects_out_of_range(client, db_session):
    _profile(db_session)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.patch("/api/profiles/me", json={"fluency_threshold": 0}, headers=headers)
    assert resp.status_code == 422

    resp = client.patch("/api/profiles/me", json={"fluency_threshold": 51}, headers=headers)
    assert resp.status_code == 422


def test_omitting_fluency_threshold_leaves_it_unchanged(client, db_session):
    _profile(db_session, fluency_threshold=7)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.patch("/api/profiles/me", json={}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["fluency_threshold"] == 7


# ---------------------------------------------------------------------------
# Status transitions (new -> learning -> fluent, and back)
# ---------------------------------------------------------------------------


def test_word_becomes_fluent_at_exactly_the_threshold(db_session):
    profile = _profile(db_session, fluency_threshold=3)
    word = _word(db_session)

    rate_word(db_session, profile, word.id, "knew_it")
    progress = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    assert progress.status == "learning"
    assert progress.fluent_at is None

    rate_word(db_session, profile, word.id, "knew_it")
    db_session.refresh(progress)
    assert progress.status == "learning"

    rate_word(db_session, profile, word.id, "knew_it")
    db_session.refresh(progress)
    assert progress.status == "fluent"
    assert progress.fluent_at is not None


def test_fluent_word_dropping_a_miss_reverts_to_learning_and_clears_fluent_at(db_session):
    profile = _profile(db_session, fluency_threshold=1)
    word = _word(db_session)

    rate_word(db_session, profile, word.id, "knew_it")
    progress = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    assert progress.status == "fluent"

    rate_word(db_session, profile, word.id, "didnt_know")
    db_session.refresh(progress)
    assert progress.status == "learning"
    assert progress.fluent_at is None


def test_answer_word_also_drives_fluency_status(db_session):
    profile = _profile(db_session, fluency_threshold=1)
    word = _word(db_session)

    answer_word(db_session, profile, word.id, word.id)  # correct
    progress = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    assert progress.status == "fluent"


def test_raising_threshold_does_not_retroactively_demote_already_fluent_words(db_session):
    profile = _profile(db_session, fluency_threshold=1)
    word = _word(db_session)

    rate_word(db_session, profile, word.id, "knew_it")
    progress = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    assert progress.status == "fluent"

    profile.fluency_threshold = 10
    db_session.commit()
    db_session.refresh(progress)
    assert progress.status == "fluent"  # untouched until next rating


# ---------------------------------------------------------------------------
# get_next_card excludes fluent words from the normal deck
# ---------------------------------------------------------------------------


def test_fluent_word_never_served_as_due_review(db_session):
    profile = _profile(db_session, fluency_threshold=1)
    word = _word(db_session)

    rate_word(db_session, profile, word.id, "knew_it")  # -> fluent, next_review_at is in the future though
    progress = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    # Force it due right now, as if enough time had passed — should still
    # never be served, because it's fluent.
    progress.next_review_at = datetime.now(timezone.utc)
    db_session.commit()

    card = get_next_card(db_session, profile)
    assert card is None  # nothing else in the bank, and this one word is fluent


def test_non_fluent_due_word_still_served_normally(db_session):
    profile = _profile(db_session, fluency_threshold=5)
    word = _word(db_session)

    rate_word(db_session, profile, word.id, "knew_it")
    progress = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    assert progress.status == "learning"
    progress.next_review_at = datetime.now(timezone.utc)
    db_session.commit()

    card = get_next_card(db_session, profile)
    assert card is not None
    assert card.word_pair_id == word.id
