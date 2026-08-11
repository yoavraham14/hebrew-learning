import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CefrLevel = Literal["A1", "A2", "B1", "B2"]
RatingResult = Literal["knew_it", "almost", "didnt_know"]

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

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile: ProfilePublicOut


# ---------------------------------------------------------------------------
# Cards / study flow
# ---------------------------------------------------------------------------


class CardOut(BaseModel):
    word_pair_id: int
    prompt: str
    prompt_lang: str
    reveal_english: str
    reveal_target_word: str
    reveal_target_lang: str
    reveal_phonetic: str | None
    example_target: str
    example_native: str
    part_of_speech: str
    cefr_level: str
    topic: str
    is_review: bool


class RateRequest(BaseModel):
    result: RatingResult


class RateResponse(BaseModel):
    box: int
    next_review_at: datetime


class ProgressOut(BaseModel):
    words_seen: int
    words_known: int
    current_streak: int
