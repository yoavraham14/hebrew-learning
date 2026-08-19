"""Exercise-difficulty ladder — SPEC.md-adjacent (see the exercise-ladder
plan). Five levels, keyed off UserWordProgress.exercise_level (0-4),
independent of `box` (which drives *when* a word resurfaces — see
app.services.review).

Level 0 is today's passive reveal-and-self-rate card
(app.services.cards.rate_word rates it). Levels 1-4 are all multiple-choice
— never free text, since typing is high-friction on mobile and pointless in
a script you can't read, for either profile
(app.services.cards.answer_word checks the answer objectively).

Whenever displayed text is Hebrew script and the viewing profile's native
language isn't Hebrew (i.e. the Spanish-native Hebrew-learner profile), it
is ALWAYS paired with its Spanish-reader phonetic transliteration — never
shown alone. `_text_and_phonetic` is the only place that decision is made,
so every exercise type gets it for free rather than repeating the rule at
each call site.
"""

import random
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Profile, WordPair
from app.schemas import (
    CardResponse,
    ExerciseOption,
    Lang,
    MultipleChoiceCardOut,
    RevealCardOut,
)

MAX_LEVEL = 4
PROMOTE_STREAK = 2  # consecutive correct answers at a level before advancing
NUM_OPTIONS = 4

LEVEL_NAMES: list[str] = ["reveal", "multiple_choice", "reverse", "audio_only", "fill_blank"]

# Which "side" (native vs target language) the options are drawn from, per
# level. multiple_choice/fill_blank test recognizing the TARGET word;
# reverse/audio_only test recalling what it MEANS (the native side).
_OPTIONS_SIDE_IS_TARGET: dict[int, bool] = {1: True, 2: False, 3: False, 4: True}


@dataclass(frozen=True)
class LevelTransition:
    exercise_level: int
    exercise_level_streak: int


def compute_level_transition(*, current_level: int, current_streak: int, correct: bool) -> LevelTransition:
    """Shared by both call sites — self-rated reveal cards (`correct` is
    review.LadderResult.correct) and objectively-checked MC cards (`correct`
    is the actual answer match) — so promotion/demotion behaves identically
    regardless of exercise type.

    One miss demotes a level (floor 0); PROMOTE_STREAK consecutive correct
    answers at the current level advances one (ceiling MAX_LEVEL).
    """
    if not correct:
        return LevelTransition(exercise_level=max(0, current_level - 1), exercise_level_streak=0)

    streak = current_streak + 1
    if streak >= PROMOTE_STREAK and current_level < MAX_LEVEL:
        return LevelTransition(exercise_level=current_level + 1, exercise_level_streak=0)
    return LevelTransition(exercise_level=current_level, exercise_level_streak=streak)


def _text_and_phonetic(profile: Profile, word_pair: WordPair, lang: Lang) -> tuple[str, str | None]:
    if lang == "he":
        phonetic = word_pair.phonetic_es if profile.native_lang != "he" else None
        return word_pair.hebrew_word, phonetic
    return word_pair.spanish_word, None


def _blank_out(sentence: str, target: str) -> str:
    """Replace the first occurrence of `target` in `sentence` with "____".

    Tolerates one specific mismatch: `target` is the sentence's OWN first
    word, whose leading letter is capitalized for the sentence — breaking
    a naive case-sensitive match against the stored target text, which is
    always lowercase (a word-level phonetic_es is never itself capitalized;
    only a full sentence's first letter is). Without this, a sentence-
    initial target word would silently fail to blank and reveal the
    answer outright — a real bug found while manually backfilling
    example_sentence_phonetic_es (word_generator's manual-backfill pass).
    Harmless no-op for Hebrew script, which has no case distinction.

    Falls back to returning `sentence` unblanked if `target` truly isn't
    found either way — better to show the whole sentence than crash.
    """
    if target in sentence:
        return sentence.replace(target, "____", 1)
    if sentence and sentence[0].isupper():
        lowered = sentence[0].lower() + sentence[1:]
        if target in lowered:
            return lowered.replace(target, "____", 1)
    return sentence


def _example_sentence_for_lang(word_pair: WordPair, lang: Lang) -> str:
    """The word's full (unblanked) example sentence in `lang`. Both columns
    are non-nullable — every WordPair row always has both sides, unlike
    example_sentence_phonetic_es which can still be NULL pre-backfill.
    """
    return word_pair.example_sentence_he if lang == "he" else word_pair.example_sentence_es


def _options_lang_for_level(profile: Profile, level: int) -> Lang:
    is_target = _OPTIONS_SIDE_IS_TARGET.get(level, True)
    return profile.target_lang if is_target else profile.native_lang  # type: ignore[return-value]


def correct_answer_text(profile: Profile, word_pair: WordPair, *, level: int) -> str:
    """The text (in whichever language the shown options were drawn from)
    of the correct answer for a just-answered MC card at `level`. Used to
    populate AnswerResponse.correct_text.
    """
    text, _ = _text_and_phonetic(profile, word_pair, _options_lang_for_level(profile, level))
    return text


def build_reveal_card(
    profile: Profile, word_pair: WordPair, *, is_review: bool, starred: bool = False
) -> RevealCardOut:
    native_lang: Lang = profile.native_lang  # type: ignore[assignment]
    target_lang: Lang = profile.target_lang  # type: ignore[assignment]
    prompt, _ = _text_and_phonetic(profile, word_pair, native_lang)
    reveal_target_word, reveal_phonetic = _text_and_phonetic(profile, word_pair, target_lang)
    example_target = word_pair.example_sentence_he if target_lang == "he" else word_pair.example_sentence_es
    example_native = word_pair.example_sentence_he if native_lang == "he" else word_pair.example_sentence_es
    return RevealCardOut(
        word_pair_id=word_pair.id,
        is_review=is_review,
        starred=starred,
        part_of_speech=word_pair.part_of_speech,
        cefr_level=word_pair.cefr_level,
        topic=word_pair.topic,
        prompt=prompt,
        prompt_lang=native_lang,
        reveal_english=word_pair.english_word,
        reveal_target_word=reveal_target_word,
        reveal_target_lang=target_lang,
        reveal_phonetic=reveal_phonetic,
        example_target=example_target,
        example_native=example_native,
    )


def _pick_distractors(db: Session, *, exclude_id: int, topic: str, cefr_level: str, count: int) -> list[WordPair]:
    if count <= 0:
        return []
    stmt = (
        select(WordPair)
        .where(
            WordPair.verified.is_(True),
            WordPair.id != exclude_id,
            WordPair.topic == topic,
            WordPair.cefr_level == cefr_level,
        )
        .order_by(func.random())
        .limit(count)
    )
    rows = list(db.scalars(stmt).all())
    if len(rows) < count:
        # Topic/level pool too thin — widen to any other verified word
        # rather than short the option count (best-effort, tuned during
        # build; still never includes an unverified word).
        picked_ids = {r.id for r in rows} | {exclude_id}
        fallback = db.scalars(
            select(WordPair)
            .where(WordPair.verified.is_(True), WordPair.id.not_in(picked_ids))
            .order_by(func.random())
            .limit(count - len(rows))
        ).all()
        rows.extend(fallback)
    return rows


def _build_options(db: Session, profile: Profile, word_pair: WordPair, *, lang: Lang) -> list[ExerciseOption]:
    distractors = _pick_distractors(
        db,
        exclude_id=word_pair.id,
        topic=word_pair.topic,
        cefr_level=word_pair.cefr_level,
        count=NUM_OPTIONS - 1,
    )
    options = [
        ExerciseOption(word_pair_id=wp.id, text=(pair := _text_and_phonetic(profile, wp, lang))[0], phonetic=pair[1])
        for wp in (word_pair, *distractors)
    ]
    random.shuffle(options)
    return options


def build_multiple_choice_card(
    db: Session,
    profile: Profile,
    word_pair: WordPair,
    *,
    exercise_type: str,
    is_review: bool,
    starred: bool = False,
) -> MultipleChoiceCardOut:
    native_lang: Lang = profile.native_lang  # type: ignore[assignment]
    target_lang: Lang = profile.target_lang  # type: ignore[assignment]

    prompt_text = prompt_lang = prompt_phonetic = None
    audio_text = audio_lang = None
    fill_blank_native_sentence = None
    fill_blank_sentence = None
    fill_blank_sentence_phonetic = None

    if exercise_type == "multiple_choice":
        options = _build_options(db, profile, word_pair, lang=target_lang)
        prompt_text, prompt_phonetic = _text_and_phonetic(profile, word_pair, native_lang)
        prompt_lang = native_lang
    elif exercise_type == "reverse":
        options = _build_options(db, profile, word_pair, lang=native_lang)
        prompt_text, prompt_phonetic = _text_and_phonetic(profile, word_pair, target_lang)
        prompt_lang = target_lang
        audio_text, _ = _text_and_phonetic(profile, word_pair, target_lang)
        audio_lang = target_lang
    elif exercise_type == "audio_only":
        options = _build_options(db, profile, word_pair, lang=native_lang)
        audio_text, _ = _text_and_phonetic(profile, word_pair, target_lang)
        audio_lang = target_lang
    elif exercise_type == "fill_blank":
        options = _build_options(db, profile, word_pair, lang=target_lang)

        # Shown ABOVE the blanked sentence — the full, unblanked sentence in
        # the profile's NATIVE language. This is the actual fix for
        # ambiguous fill-blank sentences: the learner already knows the
        # target concept before reading the target-language sentence, so
        # the task becomes "recall the word for this known meaning," not
        # "guess which word fits this context" — the target sentence no
        # longer has to be self-disambiguating on its own (see
        # gemini_client._SENTENCE_SPECIFICITY_RULES for the corresponding
        # prompt-side relaxation). Always populated — both example_sentence
        # columns are non-nullable.
        fill_blank_native_sentence = _example_sentence_for_lang(word_pair, native_lang)

        sentence = _example_sentence_for_lang(word_pair, target_lang)
        target_text, _ = _text_and_phonetic(profile, word_pair, target_lang)
        fill_blank_sentence = _blank_out(sentence, target_text)

        # Full-sentence Spanish-phonetic transliteration, blanked the same
        # best-effort way as the Hebrew sentence above — only meaningful
        # when reading Hebrew script as a non-Hebrew-native (same gate
        # _text_and_phonetic uses for the per-word phonetic_es), and only
        # once the word's sentence has been backfilled with one (NULL
        # until then — see word_pair.example_sentence_phonetic_es).
        if target_lang == "he" and profile.native_lang != "he" and word_pair.example_sentence_phonetic_es:
            fill_blank_sentence_phonetic = _blank_out(word_pair.example_sentence_phonetic_es, word_pair.phonetic_es)
    else:
        raise ValueError(f"unknown exercise_type: {exercise_type!r}")

    return MultipleChoiceCardOut(
        exercise_type=exercise_type,
        word_pair_id=word_pair.id,
        is_review=is_review,
        starred=starred,
        part_of_speech=word_pair.part_of_speech,
        cefr_level=word_pair.cefr_level,
        topic=word_pair.topic,
        prompt_text=prompt_text,
        prompt_lang=prompt_lang,
        prompt_phonetic=prompt_phonetic,
        audio_text=audio_text,
        audio_lang=audio_lang,
        fill_blank_native_sentence=fill_blank_native_sentence,
        fill_blank_sentence=fill_blank_sentence,
        fill_blank_sentence_phonetic=fill_blank_sentence_phonetic,
        options=options,
    )


def build_card(
    db: Session, profile: Profile, word_pair: WordPair, *, level: int, is_review: bool, starred: bool = False
) -> CardResponse:
    if level <= 0:
        return build_reveal_card(profile, word_pair, is_review=is_review, starred=starred)
    exercise_type = LEVEL_NAMES[min(level, MAX_LEVEL)]
    return build_multiple_choice_card(
        db, profile, word_pair, exercise_type=exercise_type, is_review=is_review, starred=starred
    )
