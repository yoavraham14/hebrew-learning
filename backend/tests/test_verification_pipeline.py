"""Coverage for the two-stage generation pipeline in
app.services.word_generator.run_generation_batch: stage 1 (generate, mocked
here — its own schema validation is covered by
test_word_schema_validation.py) and stage 2 (verify), including the
cost-firewall interaction between the two real Gemini calls.

generate_word_batch and verify_word_batch are monkeypatched at the
word_generator module level (where they're imported into) so no real network
call is ever made.
"""

from app.config import get_settings
from app.models import GenerationCallLog, GenerationStatus, WordPair
from app.schemas import GeneratedWordBatch, GeneratedWordItem, VerificationBatch, VerificationItem
from app.services import word_generator
from app.services.gemini_client import GeminiBillingError, GeminiGenerationError


def _item(n: int, **overrides) -> GeneratedWordItem:
    data = {
        "hebrew_word": f"מילה{n}",
        "phonetic_en": f"mila{n}",
        "phonetic_es": f"milá{n}",
        "spanish_word": f"palabra{n}",
        "english_word": f"word{n}",
        "part_of_speech": "noun",
        "cefr_level": "A1",
        "topic": "home",
        "example_sentence_he": f"זו מילה{n}.",
        "example_sentence_es": f"Esta es palabra{n}.",
        "example_sentence_phonetic_es": f"Zo milá{n}.",
    }
    data.update(overrides)
    return GeneratedWordItem.model_validate(data)


def _wordpairs(db_session) -> list[WordPair]:
    return list(db_session.query(WordPair).order_by(WordPair.id).all())


def test_all_ok_batch_inserted_and_verified(db_session, monkeypatch):
    items = [_item(1), _item(2)]
    monkeypatch.setattr(word_generator, "generate_word_batch", lambda **kw: GeneratedWordBatch(words=items))
    monkeypatch.setattr(
        word_generator,
        "verify_word_batch",
        lambda **kw: VerificationBatch(
            results=[VerificationItem(index=0, status="ok"), VerificationItem(index=1, status="ok")]
        ),
    )

    inserted = word_generator.run_generation_batch(db_session)

    assert inserted == 2
    rows = _wordpairs(db_session)
    assert len(rows) == 2
    assert all(row.verified for row in rows)

    log = db_session.query(GenerationCallLog).one()
    assert log.api_calls_made == 2
    assert log.verify_status == "success"
    assert log.words_verified_ok == 2


def test_mixed_ok_corrected_reject(db_session, monkeypatch):
    items = [_item(1), _item(2), _item(3)]
    corrected = _item(2, spanish_word="palabra-corregida")
    monkeypatch.setattr(word_generator, "generate_word_batch", lambda **kw: GeneratedWordBatch(words=items))
    monkeypatch.setattr(
        word_generator,
        "verify_word_batch",
        lambda **kw: VerificationBatch(
            results=[
                VerificationItem(index=0, status="ok"),
                VerificationItem(index=1, status="corrected", corrected=corrected, note="fixed register"),
                VerificationItem(index=2, status="reject", note="not a real word"),
            ]
        ),
    )

    inserted = word_generator.run_generation_batch(db_session)

    assert inserted == 3  # rejected items are still inserted, just flagged
    rows = {row.hebrew_word: row for row in _wordpairs(db_session)}

    ok_row = rows[items[0].hebrew_word]
    assert ok_row.verified is True

    corrected_row = rows[items[1].hebrew_word]
    assert corrected_row.verified is True
    assert corrected_row.spanish_word == "palabra-corregida"  # stored content is the CORRECTED text
    assert corrected_row.verification_note == "fixed register"

    reject_row = rows[items[2].hebrew_word]
    assert reject_row.verified is False
    assert reject_row.verification_note == "not a real word"
    assert reject_row.spanish_word == items[2].spanish_word  # original text kept, not discarded


def test_verify_billing_error_halts_generation_and_keeps_stage1_words_unverified(db_session, monkeypatch):
    items = [_item(1)]
    monkeypatch.setattr(word_generator, "generate_word_batch", lambda **kw: GeneratedWordBatch(words=items))

    def _raise_billing(**kw):
        raise GeminiBillingError("prepayment credits depleted")

    monkeypatch.setattr(word_generator, "verify_word_batch", _raise_billing)

    inserted = word_generator.run_generation_batch(db_session)

    assert inserted == 1  # stage-1 words are still inserted, just unverified
    row = _wordpairs(db_session)[0]
    assert row.verified is False

    status = word_generator.get_or_create_status(db_session)
    assert status.halted is True
    assert "prepayment credits" in status.halted_reason

    log = db_session.query(GenerationCallLog).one()
    assert log.api_calls_made == 2
    assert log.verify_status == "error"


def test_verify_generic_error_inserts_stage1_words_unverified_without_halting(db_session, monkeypatch):
    items = [_item(1)]
    monkeypatch.setattr(word_generator, "generate_word_batch", lambda **kw: GeneratedWordBatch(words=items))

    def _raise_generic(**kw):
        raise GeminiGenerationError("malformed JSON from verify call")

    monkeypatch.setattr(word_generator, "verify_word_batch", _raise_generic)

    inserted = word_generator.run_generation_batch(db_session)

    assert inserted == 1
    assert _wordpairs(db_session)[0].verified is False

    status = word_generator.get_or_create_status(db_session)
    assert status.halted is False  # a non-billing error must never halt generation

    log = db_session.query(GenerationCallLog).one()
    assert log.verify_status == "error"


def test_verify_skipped_when_it_would_exceed_the_daily_cap(db_session, monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_CALL_CAP", "1")
    get_settings.cache_clear()
    try:
        items = [_item(1)]
        monkeypatch.setattr(word_generator, "generate_word_batch", lambda **kw: GeneratedWordBatch(words=items))

        def _fail_if_called(**kw):
            raise AssertionError("verify_word_batch must not be called once the cap would be exceeded")

        monkeypatch.setattr(word_generator, "verify_word_batch", _fail_if_called)

        inserted = word_generator.run_generation_batch(db_session)

        assert inserted == 1
        assert _wordpairs(db_session)[0].verified is False

        log = db_session.query(GenerationCallLog).one()
        assert log.api_calls_made == 1
        assert log.verify_status == "skipped_cap"
    finally:
        get_settings.cache_clear()


def test_dedup_holds_when_a_correction_collides_with_an_existing_row(db_session, monkeypatch):
    existing = WordPair(
        hebrew_word="קיים",
        phonetic_en="kayam",
        phonetic_es="kaiám",
        spanish_word="existente",
        english_word="existing",
        part_of_speech="adjective",
        cefr_level="A1",
        topic="home",
        example_sentence_he="זה קיים.",
        example_sentence_es="Esto es existente.",
        verified=True,
    )
    db_session.add(existing)
    db_session.commit()

    items = [_item(1)]  # generated as a distinct word...
    # ...but the verification pass "corrects" it into exactly the row above.
    corrected = GeneratedWordItem(
        hebrew_word="קיים",
        phonetic_en="kayam",
        phonetic_es="kaiám",
        spanish_word="existente",
        english_word="existing",
        part_of_speech="adjective",
        cefr_level="A1",
        topic="home",
        example_sentence_he="זה קיים.",
        example_sentence_es="Esto es existente.",
        example_sentence_phonetic_es="Ze kaiám.",
    )
    monkeypatch.setattr(word_generator, "generate_word_batch", lambda **kw: GeneratedWordBatch(words=items))
    monkeypatch.setattr(
        word_generator,
        "verify_word_batch",
        lambda **kw: VerificationBatch(
            results=[VerificationItem(index=0, status="corrected", corrected=corrected, note="normalized")]
        ),
    )

    inserted = word_generator.run_generation_batch(db_session)

    assert inserted == 0  # collided with the pre-existing row, correctly skipped
    assert len(_wordpairs(db_session)) == 1  # no duplicate inserted
