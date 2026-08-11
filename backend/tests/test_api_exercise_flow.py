"""API-level coverage for the exercise ladder + answer endpoint, on top of
the existing reveal-only flow in test_api_cards_flow.py.
"""

from app.models import Profile, WordPair
from app.security import hash_pin


def _login(client, slug: str, pin: str) -> dict:
    resp = client.post("/api/auth/login", json={"profile_slug": slug, "pin": pin})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _seed(db_session, count: int = 4) -> list[WordPair]:
    profile = Profile(
        slug="hebrew_learner", display_name="Hebrew Learner", native_lang="es", target_lang="he",
        pin_hash=hash_pin("1234"),
    )
    db_session.add(profile)
    words = []
    for i in range(count):
        w = WordPair(
            hebrew_word=f"מילה{i}", phonetic_en=f"mila{i}", phonetic_es=f"milá{i}",
            spanish_word=f"palabra{i}", english_word=f"word{i}", part_of_speech="noun",
            cefr_level="A1", topic="home",
            example_sentence_he=f"זו מילה{i}.", example_sentence_es=f"Esta es palabra{i}.",
            verified=True,
        )
        db_session.add(w)
        words.append(w)
    db_session.commit()
    return words


def test_two_correct_reveal_ratings_promote_to_multiple_choice(client, db_session):
    _seed(db_session)
    headers = _login(client, "hebrew_learner", "1234")

    card = client.get("/api/cards/next", headers=headers).json()
    assert card["exercise_type"] == "reveal"
    word_id = card["word_pair_id"]

    r1 = client.post(f"/api/cards/{word_id}/rate", json={"result": "knew_it"}, headers=headers).json()
    assert r1["exercise_level"] == 0  # first correct just builds streak, doesn't promote yet

    r2 = client.post(f"/api/cards/{word_id}/rate", json={"result": "knew_it"}, headers=headers).json()
    assert r2["exercise_level"] == 1  # second consecutive correct promotes (PROMOTE_STREAK = 2)

    # Next time this word is due it should surface as multiple_choice, not reveal.
    # Force it due now by re-fetching — box advanced but interval starts at 1 day,
    # so instead assert directly against the stored progress via the progress endpoint
    # would need more plumbing; simplest: query the DB.
    from app.models import UserWordProgress

    progress = (
        db_session.query(UserWordProgress)
        .filter_by(word_pair_id=word_id)
        .one()
    )
    assert progress.exercise_level == 1


def test_answer_endpoint_correct_advances_box_and_streak(client, db_session):
    words = _seed(db_session, count=4)
    headers = _login(client, "hebrew_learner", "1234")

    from datetime import datetime, timezone

    from app.models import UserWordProgress

    # Put the first word straight at level 1 so /next returns multiple_choice.
    progress = UserWordProgress(
        profile_id=1, word_pair_id=words[0].id, exercise_level=1, next_review_at=datetime.now(timezone.utc)
    )
    db_session.add(progress)
    db_session.commit()

    card = client.get("/api/cards/next", headers=headers).json()
    assert card["exercise_type"] == "multiple_choice"
    assert card["word_pair_id"] == words[0].id
    correct_option = next(opt for opt in card["options"] if opt["word_pair_id"] == words[0].id)

    resp = client.post(
        f"/api/cards/{words[0].id}/answer",
        json={"selected_word_pair_id": correct_option["word_pair_id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is True
    assert body["correct_word_pair_id"] == words[0].id
    assert body["box"] == 1  # advanced from box 0


def test_answer_endpoint_wrong_demotes_and_records_recent_miss(client, db_session):
    words = _seed(db_session, count=4)
    headers = _login(client, "hebrew_learner", "1234")

    from datetime import datetime, timezone

    from app.models import UserWordProgress

    progress = UserWordProgress(
        profile_id=1, word_pair_id=words[0].id, exercise_level=2, next_review_at=datetime.now(timezone.utc)
    )
    db_session.add(progress)
    db_session.commit()

    card = client.get("/api/cards/next", headers=headers).json()
    assert card["exercise_type"] == "reverse"
    wrong_option = next(opt for opt in card["options"] if opt["word_pair_id"] != words[0].id)

    resp = client.post(
        f"/api/cards/{words[0].id}/answer",
        json={"selected_word_pair_id": wrong_option["word_pair_id"]},
        headers=headers,
    )
    body = resp.json()
    assert body["correct"] is False
    assert body["correct_word_pair_id"] == words[0].id
    assert body["box"] == 0  # reset by "didnt_know"-equivalent

    from app.models import RecentMiss

    misses = db_session.query(RecentMiss).filter_by(word_pair_id=words[0].id).all()
    assert len(misses) == 1

    db_session.refresh(progress)
    assert progress.exercise_level == 1  # demoted one level


def test_answer_endpoint_requires_auth(client, db_session):
    words = _seed(db_session, count=4)
    resp = client.post(f"/api/cards/{words[0].id}/answer", json={"selected_word_pair_id": words[0].id})
    assert resp.status_code == 401
