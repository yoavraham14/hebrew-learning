from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    """A learner profile. There are exactly two in this app (Hebrew learner,
    Spanish learner), seeded by scripts/seed_profiles.py. This row IS the
    user identity — see SPEC.md §3.
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    # ISO-639-1-ish codes: "es" or "he"
    native_lang: Mapped[str] = mapped_column(String(8))
    target_lang: Mapped[str] = mapped_column(String(8))
    pin_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Daily streak bookkeeping — updated on every rating (SPEC.md §5).
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class WordPair(Base):
    """One Hebrew<->Spanish<->English word concept, shared by both profiles
    (see SPEC.md §2.2). Direction of study is decided at read time by the
    profile, not baked into the row.
    """

    __tablename__ = "word_pairs"
    __table_args__ = (UniqueConstraint("hebrew_word", "spanish_word", name="uq_word_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    hebrew_word: Mapped[str] = mapped_column(String(128))
    # English-reader-style transliteration of hebrew_word.
    phonetic_en: Mapped[str] = mapped_column(String(128))
    # Spanish-reader-style transliteration of hebrew_word — the one actually
    # shown to the Hebrew-learner profile. This is the field that must not
    # be wrong (SPEC.md §1.1).
    phonetic_es: Mapped[str] = mapped_column(String(128))

    spanish_word: Mapped[str] = mapped_column(String(128))
    english_word: Mapped[str] = mapped_column(String(128))

    part_of_speech: Mapped[str] = mapped_column(String(32))
    cefr_level: Mapped[str] = mapped_column(String(4))
    topic: Mapped[str] = mapped_column(String(64))

    example_sentence_he: Mapped[str] = mapped_column(Text)
    example_sentence_es: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserWordProgress(Base):
    """Per-(profile, word) review state. `box` drives the v1 interval ladder;
    `repetitions`/`ease_factor`/`interval_days` are populated but unused by
    v1 logic so a full SM-2 scheduler can be dropped in later without a
    migration (SPEC.md §4.1).
    """

    __tablename__ = "user_word_progress"
    __table_args__ = (
        UniqueConstraint("profile_id", "word_pair_id", name="uq_profile_word"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    word_pair_id: Mapped[int] = mapped_column(ForeignKey("word_pairs.id", ondelete="CASCADE"), index=True)

    box: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[float] = mapped_column(Float, default=0)
    next_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_result: Mapped[str | None] = mapped_column(String(16), nullable=True)

    times_seen: Mapped[int] = mapped_column(Integer, default=0)
    times_correct: Mapped[int] = mapped_column(Integer, default=0)

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    word_pair: Mapped["WordPair"] = relationship(lazy="joined")


class GenerationCallLog(Base):
    """One row per Gemini generation call — the audit trail behind the daily
    cap in SPEC.md §2.1.
    """

    __tablename__ = "generation_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    batch_size_requested: Mapped[int] = mapped_column(Integer)
    words_inserted: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16))  # "success" | "error"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class GenerationStatus(Base):
    """Single-row table (id=1) holding the global generation kill-switch
    state. Once `halted` is set (billing-related error from Gemini), no
    further generation calls are made until an operator investigates and
    manually clears it — never automatically. See SPEC.md §2.1.
    """

    __tablename__ = "generation_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    halted: Mapped[bool] = mapped_column(Boolean, default=False)
    halted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    halted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
