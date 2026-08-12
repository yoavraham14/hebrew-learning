from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
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

    # Lifetime count of ratings/answers of any exercise type — drives the
    # recovery-round (every 15) and mixed-round (every 30) triggers.
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)

    # How many times a word must be marked/answered "knew it" (see
    # UserWordProgress.status) before it counts as fluent and leaves the
    # normal deck — see app.services.cards._apply_result. User-editable at
    # any time via PATCH /api/profiles/me, not just at creation.
    fluency_threshold: Mapped[int] = mapped_column(Integer, default=3)

    # Progress-page stats (feature pass, stage C). daily_goal is a target
    # review count per day, user-editable via PATCH /api/profiles/me
    # alongside fluency_threshold; today's actual count lives in
    # DailyActivity, not here. longest_streak only ever grows — updated
    # in app.services.cards._apply_result whenever current_streak does.
    daily_goal: Mapped[int] = mapped_column(Integer, default=10)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)


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

    # Set by the stage-2 verification pass (SPEC.md-adjacent — see the
    # translation-verification feature). Only verified words are ever
    # selected for a card; unverified ones sit in the bank until a future
    # verification sweep. Existing pre-feature rows are grandfathered as
    # verified via the migration's server_default.
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Server-generated pronunciation audio (WAV bytes, eSpeak NG — offline,
    # no API key, no billing account, same zero-cost-risk posture as the
    # rest of this app's external-service policy). Generated lazily on
    # first request and cached here rather than at insert time, so it's
    # decoupled from the Gemini generation pipeline entirely — see
    # app.services.audio / app.routers.audio. NULL until first requested,
    # or permanently if eSpeak NG isn't installed on this machine (the
    # frontend falls back to browser TTS in that case, same as before this
    # feature existed).
    hebrew_audio: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


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

    # Exercise-difficulty ladder — independent of `box` (which drives *when*
    # a word resurfaces). `exercise_level` drives *how* it's tested: 0-4,
    # indexing app.services.exercise_ladder.LEVEL_NAMES. See that module for
    # the transition logic.
    exercise_level: Mapped[int] = mapped_column(Integer, default=0)
    exercise_level_streak: Mapped[int] = mapped_column(Integer, default=0)

    # "new" | "learning" | "fluent" — recomputed on every rate/answer from
    # `repetitions` vs. the profile's `fluency_threshold` (see
    # app.services.cards._apply_result). "new" is effectively transient: a
    # row is only ever created together with its first rating in the same
    # request, so it's overwritten to "learning"/"fluent" before anything
    # ever reads it back — it exists mainly as the honest pre-first-rating
    # default. Recomputing on every write (rather than a one-way ratchet)
    # is deliberate: a fluent word that gets missed in a mixed round drops
    # back to "learning" and re-enters the normal deck automatically,
    # which is the whole point of testing it periodically.
    status: Mapped[str] = mapped_column(String(16), default="new")
    # Set when status transitions TO "fluent"; cleared when it drops back
    # out. Powers "became fluent this week" in the weekly summary — a
    # later feature stage, not read anywhere yet.
    fluent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    word_pair: Mapped["WordPair"] = relationship(lazy="joined")


class RecentMiss(Base):
    """A word a profile just got wrong (rated almost/didnt_know, or answered
    an objective exercise incorrectly). The pool a recovery round draws
    from — rows are deleted once served in a round (SPEC.md-adjacent — see
    the review-games feature).
    """

    __tablename__ = "recent_miss"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    word_pair_id: Mapped[int] = mapped_column(ForeignKey("word_pairs.id", ondelete="CASCADE"))
    missed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    word_pair: Mapped["WordPair"] = relationship(lazy="joined")


class DailyActivity(Base):
    """One row per (profile, calendar day) that had any activity — upserted
    in app.services.cards._apply_result on every rate/answer. Backs the
    progress page's daily-goal-vs-today card, and later feature-pass stages
    (activity calendar, weekly summary) reuse this same table rather than
    each inventing their own daily aggregate.
    """

    __tablename__ = "daily_activity"
    __table_args__ = (UniqueConstraint("profile_id", "activity_date", name="uq_profile_activity_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    activity_date: Mapped[date] = mapped_column(Date, index=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)


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

    # How many real Gemini requests this run actually made (1 = generate
    # only; 2 = generate + verify). _count_calls_today sums this column, not
    # row count, so the daily cap correctly counts both stages.
    api_calls_made: Mapped[int] = mapped_column(Integer, default=1)
    verify_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "success"|"error"|"skipped_cap"
    words_verified_ok: Mapped[int] = mapped_column(Integer, default=0)


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
