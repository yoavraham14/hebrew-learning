from app.models import Profile, WordPair
from app.security import hash_pin
from app.services import exercise_ladder
from app.services.exercise_ladder import (
    MAX_LEVEL,
    NUM_OPTIONS,
    PROMOTE_STREAK,
    compute_level_transition,
)


# ---------------------------------------------------------------------------
# compute_level_transition — pure function, no DB needed
# ---------------------------------------------------------------------------


def test_correct_answer_builds_streak_without_promoting_before_threshold():
    result = compute_level_transition(current_level=1, current_streak=0, correct=True)
    assert result.exercise_level == 1
    assert result.exercise_level_streak == 1


def test_correct_answer_promotes_once_streak_hits_threshold():
    result = compute_level_transition(current_level=1, current_streak=PROMOTE_STREAK - 1, correct=True)
    assert result.exercise_level == 2
    assert result.exercise_level_streak == 0  # resets after promotion


def test_incorrect_answer_demotes_and_resets_streak():
    result = compute_level_transition(current_level=2, current_streak=1, correct=False)
    assert result.exercise_level == 1
    assert result.exercise_level_streak == 0


def test_level_floor_never_goes_below_zero():
    result = compute_level_transition(current_level=0, current_streak=0, correct=False)
    assert result.exercise_level == 0


def test_level_ceiling_never_exceeds_max_level():
    result = compute_level_transition(current_level=MAX_LEVEL, current_streak=PROMOTE_STREAK - 1, correct=True)
    assert result.exercise_level == MAX_LEVEL
    # streak still counts up rather than resetting, since there's nowhere to promote to
    assert result.exercise_level_streak == PROMOTE_STREAK


# ---------------------------------------------------------------------------
# Card building — needs a DB (distractor pool) and two profile directions
# ---------------------------------------------------------------------------


_seed_counter = 0


def _seed_words(db_session, count: int, *, topic: str = "home", cefr_level: str = "A1", verified: bool = True):
    global _seed_counter
    words = []
    for _ in range(count):
        i = _seed_counter
        _seed_counter += 1
        w = WordPair(
            hebrew_word=f"מילה{i}",
            phonetic_en=f"mila{i}",
            phonetic_es=f"milá{i}",
            spanish_word=f"palabra{i}",
            english_word=f"word{i}",
            part_of_speech="noun",
            cefr_level=cefr_level,
            topic=topic,
            example_sentence_he=f"זו מילה{i} טובה.",
            example_sentence_es=f"Esta es una palabra{i} buena.",
            verified=verified,
        )
        db_session.add(w)
        words.append(w)
    db_session.commit()
    return words


def _hebrew_learner(db_session) -> Profile:
    # Native Spanish, target Hebrew — the profile that can't read Hebrew
    # script and must always get a phonetic alongside it.
    p = Profile(
        slug="hebrew_learner", display_name="Hebrew Learner", native_lang="es", target_lang="he",
        pin_hash=hash_pin("1234"),
    )
    db_session.add(p)
    db_session.commit()
    return p


def _spanish_learner(db_session) -> Profile:
    # Native Hebrew, target Spanish — reads Hebrew natively, so never needs
    # a phonetic for it.
    p = Profile(
        slug="spanish_learner", display_name="Spanish Learner", native_lang="he", target_lang="es",
        pin_hash=hash_pin("5678"),
    )
    db_session.add(p)
    db_session.commit()
    return p


def test_multiple_choice_options_for_hebrew_learner_always_carry_phonetic(db_session):
    profile = _hebrew_learner(db_session)
    words = _seed_words(db_session, 5)

    card = exercise_ladder.build_multiple_choice_card(
        db_session, profile, words[0], exercise_type="multiple_choice", is_review=False
    )

    assert len(card.options) == NUM_OPTIONS
    # multiple_choice options are TARGET-language (Hebrew) — every one must
    # carry a phonetic, since this profile can't read Hebrew script.
    for option in card.options:
        assert option.phonetic is not None


def test_reverse_options_for_hebrew_learner_are_native_language_no_phonetic_needed(db_session):
    profile = _hebrew_learner(db_session)
    words = _seed_words(db_session, 5)

    card = exercise_ladder.build_multiple_choice_card(
        db_session, profile, words[0], exercise_type="reverse", is_review=False
    )

    # reverse options are NATIVE-language (Spanish) — Latin script, no
    # phonetic needed regardless of profile.
    for option in card.options:
        assert option.phonetic is None
    # ...but the PROMPT (target-language, Hebrew) must carry one.
    assert card.prompt_lang == "he"
    assert card.prompt_phonetic is not None


def test_spanish_learner_never_gets_a_phonetic_for_their_native_hebrew(db_session):
    profile = _spanish_learner(db_session)
    words = _seed_words(db_session, 5)

    # audio_only options are native-language (Hebrew, for this profile) —
    # but Hebrew IS their native script, so no phonetic is ever attached.
    card = exercise_ladder.build_multiple_choice_card(
        db_session, profile, words[0], exercise_type="audio_only", is_review=False
    )
    for option in card.options:
        assert option.phonetic is None


def test_options_never_include_unverified_words(db_session):
    profile = _hebrew_learner(db_session)
    verified_words = _seed_words(db_session, 2, topic="home", verified=True)
    _seed_words(db_session, 10, topic="home", verified=False)

    card = exercise_ladder.build_multiple_choice_card(
        db_session, profile, verified_words[0], exercise_type="multiple_choice", is_review=False
    )

    option_ids = {opt.word_pair_id for opt in card.options}
    # Only 2 verified words exist total, so options can't be padded to 4 —
    # this also proves the unverified pool was never touched as a fallback.
    assert option_ids == {w.id for w in verified_words}


def test_options_never_duplicate_the_correct_answer(db_session):
    profile = _hebrew_learner(db_session)
    words = _seed_words(db_session, 8)

    card = exercise_ladder.build_multiple_choice_card(
        db_session, profile, words[0], exercise_type="multiple_choice", is_review=False
    )

    option_ids = [opt.word_pair_id for opt in card.options]
    assert len(option_ids) == len(set(option_ids))  # no duplicates
    assert words[0].id in option_ids  # the correct answer is present


def test_fill_blank_sentence_blanks_out_the_target_word(db_session):
    profile = _hebrew_learner(db_session)
    words = _seed_words(db_session, 4)

    card = exercise_ladder.build_multiple_choice_card(
        db_session, profile, words[0], exercise_type="fill_blank", is_review=False
    )

    assert "____" in card.fill_blank_sentence
    assert words[0].hebrew_word not in card.fill_blank_sentence


def test_build_card_level_zero_is_reveal(db_session):
    profile = _hebrew_learner(db_session)
    words = _seed_words(db_session, 1)

    card = exercise_ladder.build_card(db_session, profile, words[0], level=0, is_review=False)
    assert card.exercise_type == "reveal"


def test_build_card_level_one_is_multiple_choice(db_session):
    profile = _hebrew_learner(db_session)
    words = _seed_words(db_session, 4)

    card = exercise_ladder.build_card(db_session, profile, words[0], level=1, is_review=True)
    assert card.exercise_type == "multiple_choice"


def test_correct_answer_text_matches_options_language():
    from app.models import Profile as ProfileModel

    hebrew_learner = ProfileModel(
        slug="x", display_name="x", native_lang="es", target_lang="he", pin_hash="x"
    )
    word = WordPair(
        hebrew_word="חלון", phonetic_en="chalon", phonetic_es="jalón", spanish_word="ventana",
        english_word="window", part_of_speech="noun", cefr_level="A1", topic="home",
        example_sentence_he="x", example_sentence_es="x", verified=True,
    )
    # level 1 (multiple_choice) options are target-language (Hebrew)
    assert exercise_ladder.correct_answer_text(hebrew_learner, word, level=1) == "חלון"
    # level 2 (reverse) options are native-language (Spanish)
    assert exercise_ladder.correct_answer_text(hebrew_learner, word, level=2) == "ventana"
