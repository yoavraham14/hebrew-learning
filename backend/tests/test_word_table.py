"""Stage D of the progress-page/study-flow feature pass: the word table
(GET /api/progress/words, mark-fluent, reset) and starring.
"""

from datetime import datetime, timedelta, timezone

from app.models import Profile, UserWordProgress, WordPair
from app.security import hash_pin
from app.services.cards import rate_word
from app.services.progress import list_word_progress, mark_fluent, reset_word, set_starred


def _aware(dt: datetime) -> datetime:
    """SQLite (test DB only — Postgres preserves tz correctly) drops tzinfo
    on read-back; re-attach UTC so arithmetic against an aware `now` works.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


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


def _login(client, slug: str, pin: str) -> dict:
    resp = client.post("/api/auth/login", json={"profile_slug": slug, "pin": pin})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# list_word_progress
# ---------------------------------------------------------------------------


def test_list_word_progress_includes_seen_words_with_computed_accuracy(db_session):
    profile = _profile(db_session)
    word = _word(db_session)

    rate_word(db_session, profile, word.id, "knew_it")
    rate_word(db_session, profile, word.id, "didnt_know")

    rows = list_word_progress(db_session, profile)
    assert len(rows) == 1
    assert rows[0].word_pair_id == word.id
    assert rows[0].times_seen == 2
    assert rows[0].times_correct == 1
    assert rows[0].accuracy == 50.0


def test_list_word_progress_excludes_unseen_words(db_session):
    profile = _profile(db_session)
    _word(db_session)  # never rated
    assert list_word_progress(db_session, profile) == []


# ---------------------------------------------------------------------------
# mark_fluent / reset_word
# ---------------------------------------------------------------------------


def test_mark_fluent_overrides_status_immediately(db_session):
    profile = _profile(db_session, fluency_threshold=50)  # would never organically qualify
    word = _word(db_session)
    rate_word(db_session, profile, word.id, "knew_it")

    result = mark_fluent(db_session, profile, word.id)
    assert result.status == "fluent"
    assert result.fluent_at is not None


def test_reset_word_zeroes_stats_but_keeps_the_row_and_starred(db_session):
    profile = _profile(db_session, fluency_threshold=1)
    word = _word(db_session)
    rate_word(db_session, profile, word.id, "knew_it")  # -> fluent, times_seen=1
    set_starred(db_session, profile, word.id, True)

    result = reset_word(db_session, profile, word.id)
    assert result.status == "new"
    assert result.times_seen == 0
    assert result.times_correct == 0
    assert result.fluent_at is None
    assert result.starred is True  # untouched — preference, not progress

    # Row still exists (word table's "every word seen" still includes it).
    rows = list_word_progress(db_session, profile)
    assert len(rows) == 1


def test_reset_word_re_enters_the_normal_deck(db_session):
    from app.services.cards import get_next_card

    profile = _profile(db_session, fluency_threshold=1)
    word = _word(db_session)
    rate_word(db_session, profile, word.id, "knew_it")  # -> fluent, leaves the deck
    assert get_next_card(db_session, profile) is None

    reset_word(db_session, profile, word.id)
    card = get_next_card(db_session, profile)
    assert card is not None
    assert card.word_pair_id == word.id


# ---------------------------------------------------------------------------
# Starring
# ---------------------------------------------------------------------------


def test_set_starred_creates_progress_row_if_none_exists(db_session):
    profile = _profile(db_session)
    word = _word(db_session)  # never rated — no UserWordProgress row yet

    result = set_starred(db_session, profile, word.id, True)
    assert result.starred is True

    row = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    assert row.starred is True


def test_starred_word_gets_a_shorter_interval(db_session):
    profile = _profile(db_session)
    starred_word = _word(db_session, 1)
    plain_word = _word(db_session, 2)
    set_starred(db_session, profile, starred_word.id, True)

    before = datetime.now(timezone.utc)
    rate_word(db_session, profile, starred_word.id, "knew_it")
    rate_word(db_session, profile, plain_word.id, "knew_it")

    starred_progress = db_session.query(UserWordProgress).filter_by(word_pair_id=starred_word.id).one()
    plain_progress = db_session.query(UserWordProgress).filter_by(word_pair_id=plain_word.id).one()

    starred_interval = _aware(starred_progress.next_review_at) - before
    plain_interval = _aware(plain_progress.next_review_at) - before
    assert starred_interval < plain_interval
    # Halved, not just "shorter" — allow a little slack for the two calls'
    # slightly different `now` timestamps.
    assert abs(starred_interval - plain_interval / 2) < timedelta(seconds=5)


def test_unstarring_stops_the_shorter_interval(db_session):
    profile = _profile(db_session)
    word = _word(db_session)
    set_starred(db_session, profile, word.id, True)
    set_starred(db_session, profile, word.id, False)

    rate_word(db_session, profile, word.id, "knew_it")
    progress = db_session.query(UserWordProgress).filter_by(word_pair_id=word.id).one()
    assert progress.starred is False
    # Full 1-day interval (LADDER_DAYS[1]), not halved.
    assert _aware(progress.next_review_at) - datetime.now(timezone.utc) > timedelta(hours=20)


# ---------------------------------------------------------------------------
# API layer
# ---------------------------------------------------------------------------


def test_words_endpoint_requires_auth(client, db_session):
    resp = client.get("/api/progress/words")
    assert resp.status_code == 401


def test_star_endpoint_requires_auth(client, db_session):
    resp = client.post("/api/progress/words/1/star", json={"starred": True})
    assert resp.status_code == 401


def test_mark_fluent_endpoint_404s_for_unseen_word(client, db_session):
    _profile(db_session)
    _word(db_session)
    headers = _login(client, "hebrew_learner", "1234")
    resp = client.post("/api/progress/words/999999/mark-fluent", headers=headers)
    assert resp.status_code == 404


def test_full_word_table_api_flow(client, db_session):
    _profile(db_session, fluency_threshold=1)
    word = _word(db_session)
    headers = _login(client, "hebrew_learner", "1234")

    # Answer it once via the real endpoint so a progress row exists.
    next_resp = client.get("/api/cards/next", headers=headers)
    word_pair_id = next_resp.json()["word_pair_id"]
    client.post(f"/api/cards/{word_pair_id}/rate", json={"result": "knew_it"}, headers=headers)

    words_resp = client.get("/api/progress/words", headers=headers)
    assert words_resp.status_code == 200
    assert len(words_resp.json()) == 1

    star_resp = client.post(f"/api/progress/words/{word_pair_id}/star", json={"starred": True}, headers=headers)
    assert star_resp.status_code == 200
    assert star_resp.json()["starred"] is True

    reset_resp = client.post(f"/api/progress/words/{word_pair_id}/reset", headers=headers)
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "new"
    assert reset_resp.json()["starred"] is True  # survives the reset


def test_starred_state_appears_on_the_next_served_card(client, db_session):
    _profile(db_session)
    word = _word(db_session, verified=True)
    headers = _login(client, "hebrew_learner", "1234")

    card = client.get("/api/cards/next", headers=headers).json()
    assert card["starred"] is False

    client.post(f"/api/progress/words/{card['word_pair_id']}/star", json={"starred": True}, headers=headers)

    # Rate it "almost" so it stays due soon rather than fluent/gone from the deck.
    client.post(f"/api/cards/{card['word_pair_id']}/rate", json={"result": "almost"}, headers=headers)
    row = db_session.query(UserWordProgress).filter_by(word_pair_id=card["word_pair_id"]).one()
    row.next_review_at = datetime.now(timezone.utc)
    db_session.commit()

    next_card = client.get("/api/cards/next", headers=headers).json()
    assert next_card["word_pair_id"] == card["word_pair_id"]
    assert next_card["starred"] is True
