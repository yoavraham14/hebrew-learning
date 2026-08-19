import re
from datetime import date, datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

CefrLevel = Literal["A1", "A2", "B1", "B2"]
RatingResult = Literal["knew_it", "almost", "didnt_know"]
Lang = Literal["he", "es"]

_HEBREW_RANGE = re.compile(r"[֐-׿]")


# ---------------------------------------------------------------------------
# LLM generation output — validated before anything touches the DB
# (SPEC.md §2.3: "Validate every LLM response against a Pydantic schema.
# Reject and retry malformed items. Never insert unvalidated data.")
# ---------------------------------------------------------------------------


class GeneratedWordItem(BaseModel):
    hebrew_word: str = Field(min_length=1, max_length=128)
    phonetic_en: str = Field(min_length=1, max_length=128)
    phonetic_es: str = Field(min_length=1, max_length=128)
    spanish_word: str = Field(min_length=1, max_length=128)
    english_word: str = Field(min_length=1, max_length=128)
    part_of_speech: str = Field(min_length=1, max_length=32)
    cefr_level: CefrLevel
    topic: str = Field(min_length=1, max_length=64)
    example_sentence_he: str = Field(min_length=1, max_length=500)
    example_sentence_es: str = Field(min_length=1, max_length=500)
    # Spanish-phonetic transliteration of the FULL example_sentence_he (not
    # just the target word) — same purpose as phonetic_es but sentence-
    # scoped, for the fill_blank exercise's phonetic line. See
    # gemini_client._PHONETIC_RULES for the transliteration conventions.
    example_sentence_phonetic_es: str = Field(min_length=1, max_length=1000)

    @field_validator(
        "hebrew_word",
        "phonetic_en",
        "phonetic_es",
        "spanish_word",
        "english_word",
        "part_of_speech",
        "topic",
        "example_sentence_he",
        "example_sentence_es",
        "example_sentence_phonetic_es",
    )
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("hebrew_word")
    @classmethod
    def _must_contain_hebrew_script(cls, v: str) -> str:
        if not _HEBREW_RANGE.search(v):
            raise ValueError("hebrew_word must contain Hebrew script characters")
        return v

    @field_validator("example_sentence_he")
    @classmethod
    def _example_must_contain_hebrew_script(cls, v: str) -> str:
        if not _HEBREW_RANGE.search(v):
            raise ValueError("example_sentence_he must contain Hebrew script characters")
        return v


class GeneratedWordBatch(BaseModel):
    words: list[GeneratedWordItem]


# ---------------------------------------------------------------------------
# Verification pass output (stage 2) — checks the stage-1 batch for
# naturalness, register match, phonetic accuracy, and example-sentence
# usage. See app/services/gemini_client.py verify_word_batch.
# ---------------------------------------------------------------------------

VerificationStatus = Literal["ok", "corrected", "reject"]


class VerificationItem(BaseModel):
    index: int = Field(ge=0)
    status: VerificationStatus
    corrected: GeneratedWordItem | None = None
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _corrected_required_iff_status_corrected(self) -> "VerificationItem":
        if self.status == "corrected" and self.corrected is None:
            raise ValueError('corrected must be provided when status is "corrected"')
        if self.status != "corrected" and self.corrected is not None:
            # Not an error — just not the shape we asked for. Drop the
            # unused payload rather than rejecting an otherwise-fine result.
            self.corrected = None
        return self


class VerificationBatch(BaseModel):
    results: list[VerificationItem]


# ---------------------------------------------------------------------------
# Sentence backfill pipeline — regenerates just example_sentence_he/_es/
# _phonetic_es for existing WordPair rows predating the specificity/
# transliteration fix (see app.services.word_generator.
# run_sentence_backfill_batch). Correlates by word_pair_id, not array
# index, since a backfill batch spans arbitrary existing words rather than
# one topic/level-homogeneous freshly-generated batch.
# ---------------------------------------------------------------------------


class SentenceBackfillItem(BaseModel):
    word_pair_id: int
    hebrew_word: str
    spanish_word: str
    english_word: str
    part_of_speech: str
    topic: str
    cefr_level: CefrLevel
    # The existing sentence pair — sent so the backfill prompt can echo it
    # back unchanged (the common case: only example_sentence_phonetic_es
    # is actually missing) rather than needing to reinvent a sentence it
    # already has, and reserve regeneration for entries that are actually
    # defective.
    example_sentence_he: str
    example_sentence_es: str


class SentenceBackfillResult(BaseModel):
    word_pair_id: int
    example_sentence_he: str = Field(min_length=1, max_length=500)
    example_sentence_es: str = Field(min_length=1, max_length=500)
    example_sentence_phonetic_es: str = Field(min_length=1, max_length=1000)

    @field_validator("example_sentence_he", "example_sentence_es", "example_sentence_phonetic_es")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("example_sentence_he")
    @classmethod
    def _must_contain_hebrew_script(cls, v: str) -> str:
        if not _HEBREW_RANGE.search(v):
            raise ValueError("example_sentence_he must contain Hebrew script characters")
        return v


class SentenceBackfillBatch(BaseModel):
    results: list[SentenceBackfillResult]


class SentenceBackfillVerificationItem(BaseModel):
    word_pair_id: int
    status: VerificationStatus
    corrected: SentenceBackfillResult | None = None
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _corrected_required_iff_status_corrected(self) -> "SentenceBackfillVerificationItem":
        if self.status == "corrected" and self.corrected is None:
            raise ValueError('corrected must be provided when status is "corrected"')
        if self.status != "corrected" and self.corrected is not None:
            self.corrected = None
        return self


class SentenceBackfillVerificationBatch(BaseModel):
    results: list[SentenceBackfillVerificationItem]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    profile_slug: str
    pin: str


class ProfilePublicOut(BaseModel):
    slug: str
    display_name: str
    native_lang: str
    target_lang: str
    fluency_threshold: int
    daily_goal: int
    weekly_video_goal: int

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile: ProfilePublicOut


class UpdateProfileSettingsRequest(BaseModel):
    # Optional/partial — None on any field means "leave unchanged". Later
    # progress-page stages extend this same request/endpoint rather than
    # adding a new one per setting.
    fluency_threshold: int | None = Field(default=None, ge=1, le=50)
    daily_goal: int | None = Field(default=None, ge=1, le=200)
    weekly_video_goal: int | None = Field(default=None, ge=1, le=50)


# ---------------------------------------------------------------------------
# Cards / study flow
# ---------------------------------------------------------------------------


class RevealCardOut(BaseModel):
    """The original passive reveal-and-self-rate exercise — served for a
    word's first 1-2 exposures (exercise_level 0). See
    app.services.exercise_ladder.
    """

    exercise_type: Literal["reveal"] = "reveal"
    word_pair_id: int
    is_review: bool
    starred: bool = False
    part_of_speech: str
    cefr_level: str
    topic: str
    prompt: str
    prompt_lang: Lang
    reveal_english: str
    reveal_target_word: str
    reveal_target_lang: Lang
    reveal_phonetic: str | None
    example_target: str
    example_native: str


class ExerciseOption(BaseModel):
    word_pair_id: int
    text: str
    # Set only when `text` is Hebrew script and the viewing profile can't
    # read it — script and transliteration are always shown together, never
    # script alone (SPEC.md §1.1 applied to options, not just reveals).
    phonetic: str | None = None


class MultipleChoiceCardOut(BaseModel):
    """The four harder exercise types (levels 1-4) — all multiple-choice,
    never free text (see the plan's decision #3: typing is high-friction on
    mobile and pointless in a script you can't read, for either profile).
    Never carries which option is correct — that's checked server-side by
    POST /api/cards/{id}/answer.
    """

    exercise_type: Literal["multiple_choice", "reverse", "audio_only", "fill_blank"]
    word_pair_id: int
    is_review: bool
    starred: bool = False
    part_of_speech: str
    cefr_level: str
    topic: str

    # None for audio_only (nothing shown until you play the audio).
    prompt_text: str | None = None
    prompt_lang: Lang | None = None
    prompt_phonetic: str | None = None

    # Set for audio_only (required) and optionally for reverse (prompt has
    # an audio button too).
    audio_text: str | None = None
    audio_lang: Lang | None = None

    # Only for fill_blank — the FULL, unblanked sentence in the profile's
    # native language, shown ABOVE fill_blank_sentence. This is what makes
    # the exercise "recall the word for this known meaning" rather than
    # "guess from context" — see exercise_ladder.build_multiple_choice_card
    # for why this replaced trying to make the target sentence itself
    # unambiguous. Always populated when exercise_type is fill_blank.
    fill_blank_native_sentence: str | None = None
    # Only for fill_blank — the example sentence with the target word
    # blanked out. prompt_text is unused in that case.
    fill_blank_sentence: str | None = None
    # Spanish-phonetic transliteration of fill_blank_sentence (also with the
    # target word's span blanked), shown beneath it — only populated when
    # the target language is Hebrew, the profile doesn't read Hebrew
    # natively, and the word's sentence has been backfilled with a
    # transliteration (see exercise_ladder.build_multiple_choice_card).
    fill_blank_sentence_phonetic: str | None = None

    options: list[ExerciseOption]


CardResponse = Annotated[
    Union[RevealCardOut, MultipleChoiceCardOut], Field(discriminator="exercise_type")
]


class RoundOut(BaseModel):
    """A batch of review-game cards (SPEC.md-adjacent — see the review-games
    feature). Delivered as a side-channel on a rate/answer response, not as
    a different shape on GET /cards/next — see plan decision #7.
    """

    kind: Literal["recovery", "mixed", "sentence"]
    cards: list[MultipleChoiceCardOut]


class RateRequest(BaseModel):
    result: RatingResult


class AnswerRequest(BaseModel):
    selected_word_pair_id: int


class RateResponse(BaseModel):
    box: int
    next_review_at: datetime
    exercise_level: int
    round_due: RoundOut | None = None


class AnswerResponse(BaseModel):
    correct: bool
    correct_word_pair_id: int
    correct_text: str
    box: int
    exercise_level: int
    round_due: RoundOut | None = None


class ProgressOut(BaseModel):
    words_seen: int
    words_fluent: int
    # Bank-wide (not profile-specific) count of verified words — the
    # denominator for the progress bar's fluent/total ratio.
    total_verified_words: int
    current_streak: int
    longest_streak: int
    due_today: int
    daily_goal: int
    today_review_count: int

    # Video-library feature pass — see app.services.progress.get_progress
    # and app.models.WatchedVideo.
    videos_watched: int
    videos_watched_this_week: int
    weekly_video_goal: int


# ---------------------------------------------------------------------------
# Word table (progress-page feature pass, stage D) — every word this
# profile has seen, with per-word stats. Sorting/searching is client-side
# (the word bank is small by design — see SPEC.md), so this is a flat list,
# not a paginated/filterable query.
# ---------------------------------------------------------------------------


class WordProgressOut(BaseModel):
    word_pair_id: int
    hebrew_word: str
    spanish_word: str
    english_word: str
    phonetic_es: str
    topic: str
    cefr_level: str
    status: str  # "new" | "learning" | "fluent"
    starred: bool
    times_seen: int
    times_correct: int
    accuracy: float  # 0-100, times_correct/times_seen — 0 if never seen
    fluent_at: datetime | None

    model_config = {"from_attributes": True}


class SetStarredRequest(BaseModel):
    starred: bool


# ---------------------------------------------------------------------------
# Video library — standalone, not part of the study/exercise flow. See
# app.services.videos / app.models.Video / app.models.WatchedVideo.
# ---------------------------------------------------------------------------


class VideoOut(BaseModel):
    id: int
    title: str
    youtube_video_id: str
    level: str
    topic: str
    ordering: int
    # Computed per the requesting profile (app.services.videos.list_videos)
    # so the frontend never needs a second round-trip to know watch state.
    watched: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Activity calendar + weekly summary (progress-page feature pass, stage E).
# Both read DailyActivity — no new table, no new migration.
# ---------------------------------------------------------------------------


class ActivityDayOut(BaseModel):
    activity_date: date
    review_count: int
    correct_count: int

    model_config = {"from_attributes": True}


class WeeklySummaryOut(BaseModel):
    words_added: int
    words_became_fluent: int
    days_studied: int
    reviews_this_week: int
    # 0-100. 0.0 when there's no data yet for that week, not an error —
    # the frontend just doesn't show a trend arrow in that case.
    accuracy_this_week: float
    accuracy_last_week: float


# ---------------------------------------------------------------------------
# Add-user + full-profile reset (progress-page feature pass, stage G).
# ---------------------------------------------------------------------------

Direction = Literal["hebrew_learner", "spanish_learner"]


class CreateProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    pin: str = Field(min_length=4, max_length=32)
    direction: Direction


class ResetProfileRequest(BaseModel):
    password: str
    # Must exactly equal "RESET" — backend-enforced, not just a frontend
    # nicety, so the API itself refuses an accidental/scripted call that
    # only got the password right.
    confirmation: str
