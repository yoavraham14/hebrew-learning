"""Coverage for the sentence-backfill pipeline in
app.services.word_generator.run_sentence_backfill_batch: regenerating
example_sentence_he/_es/_phonetic_es for existing WordPair rows, and —
the key regression this file exists to guard — never applying a
regenerated sentence that verification didn't actually confirm.

regenerate_sentence_batch and verify_sentence_backfill_batch are
monkeypatched at the word_generator module level (where they're imported
into) so no real network call is ever made.
"""

from app.config import get_settings
from app.models import GenerationCallLog, GenerationStatus, WordPair
from app.schemas import (
    SentenceBackfillBatch,
    SentenceBackfillResult,
    SentenceBackfillVerificationBatch,
    SentenceBackfillVerificationItem,
)
from app.services import word_generator
from app.services.gemini_client import CURRENT_SENTENCE_RULES_VERSION, GeminiBillingError, GeminiGenerationError


def _word(db_session, n: int) -> WordPair:
    w = WordPair(
        hebrew_word=f"מילה{n}", phonetic_en=f"mila{n}", phonetic_es=f"milá{n}",
        spanish_word=f"palabra{n}", english_word=f"word{n}", part_of_speech="noun",
        cefr_level="A1", topic="home", example_sentence_he=f"אני אוכל מילה{n}.",
        example_sentence_es=f"Como palabra{n}.", verified=True,
    )
    db_session.add(w)
    db_session.commit()
    return w


def _result(word_pair_id: int, n: int) -> SentenceBackfillResult:
    return SentenceBackfillResult(
        word_pair_id=word_pair_id,
        example_sentence_he=f"אני שם מילה{n} בסלט.",
        example_sentence_es=f"Pongo palabra{n} en la ensalada.",
        example_sentence_phonetic_es=f"Aní sam milá{n} basalát.",
    )


def test_only_selects_rows_below_the_current_rules_version(db_session, monkeypatch):
    needs_backfill = _word(db_session, 1)  # sentence_rules_version defaults to 0
    already_current = _word(db_session, 2)
    already_current.sentence_rules_version = CURRENT_SENTENCE_RULES_VERSION
    already_current.example_sentence_phonetic_es = "ya tiene fonética"
    db_session.commit()

    seen_ids = []

    def _fake_regenerate(items):
        seen_ids.extend(item.word_pair_id for item in items)
        return SentenceBackfillBatch(results=[_result(i, 1) for i in seen_ids])

    monkeypatch.setattr(word_generator, "regenerate_sentence_batch", _fake_regenerate)
    monkeypatch.setattr(
        word_generator,
        "verify_sentence_backfill_batch",
        lambda items, results: SentenceBackfillVerificationBatch(
            results=[SentenceBackfillVerificationItem(word_pair_id=i, status="ok") for i in seen_ids]
        ),
    )

    word_generator.run_sentence_backfill_batch(db_session)

    assert seen_ids == [needs_backfill.id]


def test_reselects_rows_with_a_populated_phonetic_sentence_but_a_stale_version(db_session, monkeypatch):
    """The exact regression this design exists to prevent: a row already
    has example_sentence_phonetic_es populated (from an older, weaker
    version of the specificity rules) but its sentence_rules_version is
    stale — it must still be reselected, NOT skipped just because the
    phonetic column is non-NULL.
    """
    stale = _word(db_session, 1)
    stale.example_sentence_phonetic_es = "vieja fonética de una regla más débil"
    stale.sentence_rules_version = 0  # older than CURRENT_SENTENCE_RULES_VERSION
    db_session.commit()

    seen_ids = []
    monkeypatch.setattr(
        word_generator,
        "regenerate_sentence_batch",
        lambda items: (seen_ids.extend(i.word_pair_id for i in items), SentenceBackfillBatch(results=[_result(stale.id, 1)]))[1],
    )
    monkeypatch.setattr(
        word_generator,
        "verify_sentence_backfill_batch",
        lambda items, results: SentenceBackfillVerificationBatch(
            results=[SentenceBackfillVerificationItem(word_pair_id=stale.id, status="ok")]
        ),
    )

    updated = word_generator.run_sentence_backfill_batch(db_session)

    assert seen_ids == [stale.id]
    assert updated == 1
    db_session.refresh(stale)
    assert stale.sentence_rules_version == CURRENT_SENTENCE_RULES_VERSION
    assert stale.example_sentence_phonetic_es == _result(stale.id, 1).example_sentence_phonetic_es


def test_fully_verified_batch_updates_all_three_fields(db_session, monkeypatch):
    word = _word(db_session, 1)
    result = _result(word.id, 1)
    monkeypatch.setattr(word_generator, "regenerate_sentence_batch", lambda items: SentenceBackfillBatch(results=[result]))
    monkeypatch.setattr(
        word_generator,
        "verify_sentence_backfill_batch",
        lambda items, results: SentenceBackfillVerificationBatch(
            results=[SentenceBackfillVerificationItem(word_pair_id=word.id, status="ok")]
        ),
    )

    updated = word_generator.run_sentence_backfill_batch(db_session)

    assert updated == 1
    db_session.refresh(word)
    assert word.example_sentence_he == result.example_sentence_he
    assert word.example_sentence_es == result.example_sentence_es
    assert word.example_sentence_phonetic_es == result.example_sentence_phonetic_es
    assert word.sentence_rules_version == CURRENT_SENTENCE_RULES_VERSION

    log = db_session.query(GenerationCallLog).one()
    assert log.call_kind == "sentence_backfill"
    assert log.api_calls_made == 2
    assert log.verify_status == "success"
    assert log.words_verified_ok == 1


def test_corrected_result_is_applied_instead_of_stage1_output(db_session, monkeypatch):
    word = _word(db_session, 1)
    stage1_result = _result(word.id, 1)
    corrected = SentenceBackfillResult(
        word_pair_id=word.id,
        example_sentence_he="גרסה מתוקנת.",
        example_sentence_es="Versión corregida.",
        example_sentence_phonetic_es="Guirsá metukénet.",
    )
    monkeypatch.setattr(
        word_generator, "regenerate_sentence_batch", lambda items: SentenceBackfillBatch(results=[stage1_result])
    )
    monkeypatch.setattr(
        word_generator,
        "verify_sentence_backfill_batch",
        lambda items, results: SentenceBackfillVerificationBatch(
            results=[
                SentenceBackfillVerificationItem(
                    word_pair_id=word.id, status="corrected", corrected=corrected, note="still ambiguous"
                )
            ]
        ),
    )

    word_generator.run_sentence_backfill_batch(db_session)

    db_session.refresh(word)
    assert word.example_sentence_he == "גרסה מתוקנת."
    assert word.example_sentence_phonetic_es == "Guirsá metukénet."


def test_rejected_result_leaves_row_untouched(db_session, monkeypatch):
    word = _word(db_session, 1)
    monkeypatch.setattr(
        word_generator, "regenerate_sentence_batch", lambda items: SentenceBackfillBatch(results=[_result(word.id, 1)])
    )
    monkeypatch.setattr(
        word_generator,
        "verify_sentence_backfill_batch",
        lambda items, results: SentenceBackfillVerificationBatch(
            results=[SentenceBackfillVerificationItem(word_pair_id=word.id, status="reject", note="still bad")]
        ),
    )

    updated = word_generator.run_sentence_backfill_batch(db_session)

    assert updated == 0
    db_session.refresh(word)
    assert word.example_sentence_phonetic_es is None  # still NULL, retried next cycle
    assert word.sentence_rules_version == 0  # not bumped — still eligible next cycle

    log = db_session.query(GenerationCallLog).one()
    assert log.words_verified_ok == 0


def test_verify_skipped_for_cap_applies_nothing(db_session, monkeypatch):
    """The key regression test: an unverified stage-1 regeneration must
    NEVER be written to the DB, since undetected ambiguity is exactly the
    bug this pipeline exists to fix.
    """
    monkeypatch.setenv("GEMINI_DAILY_CALL_CAP", "1")
    get_settings.cache_clear()
    try:
        word = _word(db_session, 1)
        monkeypatch.setattr(
            word_generator,
            "regenerate_sentence_batch",
            lambda items: SentenceBackfillBatch(results=[_result(word.id, 1)]),
        )

        def _fail_if_called(items, results):
            raise AssertionError("verify_sentence_backfill_batch must not be called once the cap would be exceeded")

        monkeypatch.setattr(word_generator, "verify_sentence_backfill_batch", _fail_if_called)

        updated = word_generator.run_sentence_backfill_batch(db_session)

        assert updated == 0
        db_session.refresh(word)
        assert word.example_sentence_phonetic_es is None

        log = db_session.query(GenerationCallLog).one()
        assert log.api_calls_made == 1
        assert log.verify_status == "skipped_cap"
        assert log.words_verified_ok == 0
    finally:
        get_settings.cache_clear()


def test_verify_generic_error_applies_nothing_without_halting(db_session, monkeypatch):
    word = _word(db_session, 1)
    monkeypatch.setattr(
        word_generator, "regenerate_sentence_batch", lambda items: SentenceBackfillBatch(results=[_result(word.id, 1)])
    )

    def _raise_generic(items, results):
        raise GeminiGenerationError("malformed JSON from verify call")

    monkeypatch.setattr(word_generator, "verify_sentence_backfill_batch", _raise_generic)

    updated = word_generator.run_sentence_backfill_batch(db_session)

    assert updated == 0
    db_session.refresh(word)
    assert word.example_sentence_phonetic_es is None

    status = word_generator.get_or_create_status(db_session)
    assert status.halted is False  # a non-billing error must never halt generation


def test_verify_billing_error_halts_and_applies_nothing(db_session, monkeypatch):
    word = _word(db_session, 1)
    monkeypatch.setattr(
        word_generator, "regenerate_sentence_batch", lambda items: SentenceBackfillBatch(results=[_result(word.id, 1)])
    )

    def _raise_billing(items, results):
        raise GeminiBillingError("prepayment credits depleted")

    monkeypatch.setattr(word_generator, "verify_sentence_backfill_batch", _raise_billing)

    updated = word_generator.run_sentence_backfill_batch(db_session)

    assert updated == 0
    status = word_generator.get_or_create_status(db_session)
    assert status.halted is True
    assert "prepayment credits" in status.halted_reason


def test_stage1_billing_error_halts_generation(db_session, monkeypatch):
    _word(db_session, 1)

    def _raise_billing(items):
        raise GeminiBillingError("prepayment credits depleted")

    monkeypatch.setattr(word_generator, "regenerate_sentence_batch", _raise_billing)

    updated = word_generator.run_sentence_backfill_batch(db_session)

    assert updated == 0
    status = word_generator.get_or_create_status(db_session)
    assert status.halted is True

    log = db_session.query(GenerationCallLog).one()
    assert log.call_kind == "sentence_backfill"
    assert log.api_calls_made == 1


def test_halted_status_skips_batch_entirely(db_session, monkeypatch):
    _word(db_session, 1)
    status = word_generator.get_or_create_status(db_session)
    status.halted = True
    db_session.commit()

    def _fail_if_called(items):
        raise AssertionError("must not call regenerate_sentence_batch while halted")

    monkeypatch.setattr(word_generator, "regenerate_sentence_batch", _fail_if_called)

    updated = word_generator.run_sentence_backfill_batch(db_session)

    assert updated == 0
    assert db_session.query(GenerationCallLog).count() == 0


def test_no_eligible_rows_returns_zero_without_a_call(db_session, monkeypatch):
    def _fail_if_called(items):
        raise AssertionError("must not call regenerate_sentence_batch with nothing to backfill")

    monkeypatch.setattr(word_generator, "regenerate_sentence_batch", _fail_if_called)

    assert word_generator.run_sentence_backfill_batch(db_session) == 0
