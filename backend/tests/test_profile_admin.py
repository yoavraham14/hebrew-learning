"""Stage G of the progress-page/study-flow feature pass: add-user
(self-service profile creation) and the full-profile reset. Both are
destructive/security-sensitive, so this file is deliberately thorough —
per explicit instruction to be extra careful here.
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.models import DailyActivity, Profile, RecentMiss, UserWordProgress, WordPair
from app.security import hash_pin, verify_pin
from app.services.profiles import _slugify, create_profile, reset_profile


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
# create_profile
# ---------------------------------------------------------------------------


def test_create_profile_hebrew_learner_direction(db_session):
    profile = create_profile(db_session, display_name="Test User", pin="9999", direction="hebrew_learner")
    assert profile.native_lang == "es"
    assert profile.target_lang == "he"
    assert profile.slug == "test_user"
    assert verify_pin("9999", profile.pin_hash) is True


def test_create_profile_spanish_learner_direction(db_session):
    profile = create_profile(db_session, display_name="Another User", pin="9999", direction="spanish_learner")
    assert profile.native_lang == "he"
    assert profile.target_lang == "es"


def test_create_profile_pin_is_hashed_not_plaintext(db_session):
    profile = create_profile(db_session, display_name="Test User", pin="9999", direction="hebrew_learner")
    assert profile.pin_hash != "9999"
    assert profile.pin_hash.startswith("$2b$")  # bcrypt


def test_create_profile_slug_collision_gets_a_numeric_suffix(db_session):
    first = create_profile(db_session, display_name="Sam", pin="1111", direction="hebrew_learner")
    second = create_profile(db_session, display_name="Sam", pin="2222", direction="spanish_learner")
    assert first.slug == "sam"
    assert second.slug == "sam_2"
    assert first.slug != second.slug


def test_create_profile_does_not_collide_with_seeded_profiles(db_session):
    _profile(db_session)  # slug="hebrew_learner"
    new_profile = create_profile(db_session, display_name="Hebrew Learner", pin="1111", direction="hebrew_learner")
    assert new_profile.slug == "hebrew_learner_2"


def test_slugify_strips_non_alphanumerics_and_handles_edge_cases():
    assert _slugify("Sam Smith") == "sam_smith"
    assert _slugify("  Weird!!! Name???  ") == "weird_name"
    assert _slugify("") == "profile"
    assert _slugify("!!!") == "profile"


def test_create_profile_endpoint_requires_auth(client, db_session):
    _profile(db_session)
    resp = client.post(
        "/api/profiles", json={"display_name": "New Guy", "pin": "9999", "direction": "hebrew_learner"}
    )
    assert resp.status_code == 401


def test_create_profile_endpoint_full_flow_then_login_as_new_profile(client, db_session):
    _profile(db_session)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.post(
        "/api/profiles",
        json={"display_name": "Throwaway Test", "pin": "5555", "direction": "spanish_learner"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "throwaway_test"
    assert body["native_lang"] == "he"
    assert body["target_lang"] == "es"

    # The whole point of self-service creation: can immediately log in as it.
    login_resp = client.post(
        "/api/auth/login", json={"profile_slug": "throwaway_test", "pin": "5555"}
    )
    assert login_resp.status_code == 200


def test_create_profile_rejects_short_pin(client, db_session):
    _profile(db_session)
    headers = _login(client, "hebrew_learner", "1234")
    resp = client.post(
        "/api/profiles", json={"display_name": "X", "pin": "12", "direction": "hebrew_learner"}, headers=headers
    )
    assert resp.status_code == 422


def test_create_profile_rejects_invalid_direction(client, db_session):
    _profile(db_session)
    headers = _login(client, "hebrew_learner", "1234")
    resp = client.post(
        "/api/profiles",
        json={"display_name": "X", "pin": "9999", "direction": "martian_learner"},
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# reset_profile — the destructive one, tested thoroughly
# ---------------------------------------------------------------------------


_reset_test_word_counter = 0


def _seed_progress_for_reset_test(db_session, profile: Profile):
    """A throwaway profile with real progress data attached, so the reset
    test can verify it's actually gone afterward — not just that the
    function returns without erroring.
    """
    global _reset_test_word_counter
    _reset_test_word_counter += 1
    word = _word(db_session, _reset_test_word_counter)
    now = datetime.now(timezone.utc)
    db_session.add(
        UserWordProgress(
            profile_id=profile.id, word_pair_id=word.id, times_seen=5, times_correct=4, next_review_at=now
        )
    )
    db_session.add(RecentMiss(profile_id=profile.id, word_pair_id=word.id, missed_at=now))
    db_session.add(DailyActivity(profile_id=profile.id, activity_date=now.date(), review_count=5, correct_count=4))
    profile.total_reviews = 5
    profile.current_streak = 3
    profile.longest_streak = 3
    profile.last_activity_date = now.date()
    db_session.commit()


def test_reset_profile_wipes_all_progress_data(db_session):
    profile = _profile(db_session)
    _seed_progress_for_reset_test(db_session, profile)
    settings = get_settings()

    reset_profile(db_session, target_slug=profile.slug, password=settings.reset_password, confirmation="RESET")

    assert db_session.query(UserWordProgress).filter_by(profile_id=profile.id).count() == 0
    assert db_session.query(RecentMiss).filter_by(profile_id=profile.id).count() == 0
    assert db_session.query(DailyActivity).filter_by(profile_id=profile.id).count() == 0
    db_session.refresh(profile)
    assert profile.total_reviews == 0
    assert profile.current_streak == 0
    assert profile.longest_streak == 0
    assert profile.last_activity_date is None


def test_reset_profile_preserves_the_profile_row_and_settings(db_session):
    profile = _profile(db_session, fluency_threshold=7, daily_goal=42)
    _seed_progress_for_reset_test(db_session, profile)
    original_pin_hash = profile.pin_hash
    settings = get_settings()

    reset_profile(db_session, target_slug=profile.slug, password=settings.reset_password, confirmation="RESET")

    db_session.refresh(profile)
    assert profile.slug == "hebrew_learner"  # still exists, still logs in the same way
    assert profile.pin_hash == original_pin_hash  # PIN untouched
    assert profile.fluency_threshold == 7  # settings survive, per the clarified decision
    assert profile.daily_goal == 42


def test_reset_profile_rejects_wrong_password(db_session):
    profile = _profile(db_session)
    _seed_progress_for_reset_test(db_session, profile)

    with pytest.raises(HTTPException) as exc_info:
        reset_profile(db_session, target_slug=profile.slug, password="totally-wrong", confirmation="RESET")
    # 403, not 401 — a wrong reset password is an authorization failure for
    # an already-authenticated caller, not an identity/session problem. See
    # services/profiles.py's comment for why this distinction is load-
    # bearing (401 triggers the frontend's force-logout interceptor).
    assert exc_info.value.status_code == 403

    # Nothing was touched — the whole point of testing this explicitly.
    assert db_session.query(UserWordProgress).filter_by(profile_id=profile.id).count() == 1


def test_reset_profile_rejects_wrong_confirmation(db_session):
    profile = _profile(db_session)
    _seed_progress_for_reset_test(db_session, profile)
    settings = get_settings()

    with pytest.raises(HTTPException) as exc_info:
        reset_profile(
            db_session, target_slug=profile.slug, password=settings.reset_password, confirmation="reset"  # wrong case
        )
    assert exc_info.value.status_code == 400
    assert db_session.query(UserWordProgress).filter_by(profile_id=profile.id).count() == 1


def test_reset_profile_rejects_empty_confirmation(db_session):
    profile = _profile(db_session)
    settings = get_settings()
    with pytest.raises(HTTPException) as exc_info:
        reset_profile(db_session, target_slug=profile.slug, password=settings.reset_password, confirmation="")
    assert exc_info.value.status_code == 400


def test_reset_profile_404s_for_unknown_slug(db_session):
    settings = get_settings()
    with pytest.raises(HTTPException) as exc_info:
        reset_profile(
            db_session, target_slug="does_not_exist", password=settings.reset_password, confirmation="RESET"
        )
    assert exc_info.value.status_code == 404


def test_reset_profile_does_not_touch_other_profiles_data(db_session):
    target = _profile(db_session)
    other = _profile(db_session, slug="spanish_learner", native_lang="he", target_lang="es")
    _seed_progress_for_reset_test(db_session, target)
    _seed_progress_for_reset_test(db_session, other)
    settings = get_settings()

    reset_profile(db_session, target_slug=target.slug, password=settings.reset_password, confirmation="RESET")

    assert db_session.query(UserWordProgress).filter_by(profile_id=target.id).count() == 0
    assert db_session.query(UserWordProgress).filter_by(profile_id=other.id).count() == 1  # untouched


# ---------------------------------------------------------------------------
# API layer
# ---------------------------------------------------------------------------


def test_reset_endpoint_requires_auth(client, db_session):
    _profile(db_session)
    resp = client.post(
        "/api/profiles/hebrew_learner/reset", json={"password": "anything", "confirmation": "RESET"}
    )
    assert resp.status_code == 401


def test_reset_endpoint_wrong_password_returns_403_and_changes_nothing(client, db_session):
    """403, not 401 — see services/profiles.py's comment. A 401 here would
    trigger the frontend's global "session expired, force logout"
    interceptor, which is exactly the bug this status code choice avoids.
    """
    profile = _profile(db_session)
    _seed_progress_for_reset_test(db_session, profile)
    headers = _login(client, "hebrew_learner", "1234")

    resp = client.post(
        "/api/profiles/hebrew_learner/reset",
        json={"password": "wrong-password", "confirmation": "RESET"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert db_session.query(UserWordProgress).filter_by(profile_id=profile.id).count() == 1


def test_reset_endpoint_full_flow_with_correct_password(client, db_session):
    profile = _profile(db_session)
    _seed_progress_for_reset_test(db_session, profile)
    headers = _login(client, "hebrew_learner", "1234")
    settings = get_settings()

    resp = client.post(
        "/api/profiles/hebrew_learner/reset",
        json={"password": settings.reset_password, "confirmation": "RESET"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert db_session.query(UserWordProgress).filter_by(profile_id=profile.id).count() == 0

    # Login still works afterward — PIN untouched.
    relogin = client.post("/api/auth/login", json={"profile_slug": "hebrew_learner", "pin": "1234"})
    assert relogin.status_code == 200


def test_default_reset_password_is_the_documented_default(db_session):
    """Guards the documented default (config.py / .env.example both say
    'Qaz13579') against silent drift — if this ever fails, one of the two
    docs is now lying.
    """
    settings = get_settings()
    assert settings.reset_password == "Qaz13579"
