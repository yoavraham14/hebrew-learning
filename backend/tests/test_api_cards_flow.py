from app.models import Profile, WordPair
from app.security import hash_pin


def _seed_profile_and_word(db_session):
    profile = Profile(
        slug="hebrew_learner",
        display_name="Hebrew Learner",
        native_lang="es",
        target_lang="he",
        pin_hash=hash_pin("1234"),
    )
    db_session.add(profile)

    word = WordPair(
        hebrew_word="חלון",
        phonetic_en="chalon",
        phonetic_es="jalón",
        spanish_word="ventana",
        english_word="window",
        part_of_speech="noun",
        cefr_level="A1",
        topic="home",
        example_sentence_he="אני פותח את החלון.",
        example_sentence_es="Abro la ventana.",
        verified=True,
    )
    db_session.add(word)
    db_session.commit()


def test_full_card_flow_fetch_rate_progress(client, db_session):
    _seed_profile_and_word(db_session)

    # 1. Login
    login_resp = client.post(
        "/api/auth/login", json={"profile_slug": "hebrew_learner", "pin": "1234"}
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Fetch next card — should be the seeded word, prompted in Spanish
    # (the learner's native language for this profile), revealing Hebrew
    # script + the Spanish-reader phonetic transliteration.
    next_resp = client.get("/api/cards/next", headers=headers)
    assert next_resp.status_code == 200
    card = next_resp.json()
    assert card["prompt"] == "ventana"
    assert card["prompt_lang"] == "es"
    assert card["reveal_target_word"] == "חלון"
    assert card["reveal_target_lang"] == "he"
    assert card["reveal_phonetic"] == "jalón"
    assert card["reveal_english"] == "window"
    assert card["is_review"] is False

    # 3. Rate it "knew it" — box should advance from 0 to 1
    rate_resp = client.post(
        f"/api/cards/{card['word_pair_id']}/rate",
        json={"result": "knew_it"},
        headers=headers,
    )
    assert rate_resp.status_code == 200
    rated = rate_resp.json()
    assert rated["box"] == 1

    # 4. Progress reflects the one word seen and the streak starting
    progress_resp = client.get("/api/progress", headers=headers)
    assert progress_resp.status_code == 200
    progress = progress_resp.json()
    assert progress["words_seen"] == 1
    assert progress["current_streak"] == 1
    assert progress["words_fluent"] == 0  # repetitions=1 hasn't crossed the default threshold (3) yet


def test_login_with_wrong_pin_rejected(client, db_session):
    _seed_profile_and_word(db_session)
    resp = client.post("/api/auth/login", json={"profile_slug": "hebrew_learner", "pin": "0000"})
    assert resp.status_code == 401


def test_login_with_unknown_profile_rejected(client, db_session):
    _seed_profile_and_word(db_session)
    resp = client.post("/api/auth/login", json={"profile_slug": "nope", "pin": "1234"})
    assert resp.status_code == 401


def test_cards_next_requires_auth(client, db_session):
    _seed_profile_and_word(db_session)
    resp = client.get("/api/cards/next")
    assert resp.status_code == 401


def test_spanish_learner_direction_is_flipped(client, db_session):
    profile = Profile(
        slug="spanish_learner",
        display_name="Spanish Learner",
        native_lang="he",
        target_lang="es",
        pin_hash=hash_pin("5678"),
    )
    db_session.add(profile)
    word = WordPair(
        hebrew_word="לרקוד",
        phonetic_en="lirkod",
        phonetic_es="lirkod",
        spanish_word="bailar",
        english_word="dance",
        part_of_speech="verb",
        cefr_level="A2",
        topic="hobbies",
        example_sentence_he="אני אוהב לרקוד.",
        example_sentence_es="Me gusta bailar.",
        verified=True,
    )
    db_session.add(word)
    db_session.commit()

    login_resp = client.post(
        "/api/auth/login", json={"profile_slug": "spanish_learner", "pin": "5678"}
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    card = client.get("/api/cards/next", headers=headers).json()
    assert card["prompt"] == "לרקוד"
    assert card["prompt_lang"] == "he"
    assert card["reveal_target_word"] == "bailar"
    assert card["reveal_target_lang"] == "es"
    assert card["reveal_phonetic"] is None  # Spanish uses Latin script — no transliteration needed
