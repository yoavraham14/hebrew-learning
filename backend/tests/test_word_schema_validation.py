import pytest
from pydantic import ValidationError

from app.schemas import (
    GeneratedWordBatch,
    GeneratedWordItem,
    VerificationBatch,
    VerificationItem,
)

VALID_ITEM = {
    "hebrew_word": "חלון",
    "phonetic_en": "chalon",
    "phonetic_es": "jalón",
    "spanish_word": "ventana",
    "english_word": "window",
    "part_of_speech": "noun",
    "cefr_level": "A1",
    "topic": "home",
    "example_sentence_he": "אני פותח את החלון.",
    "example_sentence_es": "Abro la ventana.",
    "example_sentence_phonetic_es": "Aní potéaj et ajalón.",
}


def test_valid_item_passes():
    item = GeneratedWordItem.model_validate(VALID_ITEM)
    assert item.hebrew_word == "חלון"
    assert item.phonetic_es == "jalón"


def test_valid_batch_passes():
    batch = GeneratedWordBatch.model_validate({"words": [VALID_ITEM, VALID_ITEM]})
    assert len(batch.words) == 2


@pytest.mark.parametrize("field", list(VALID_ITEM.keys()))
def test_blank_field_rejected(field):
    bad = {**VALID_ITEM, field: "   "}
    with pytest.raises(ValidationError):
        GeneratedWordItem.model_validate(bad)


def test_missing_field_rejected():
    bad = {k: v for k, v in VALID_ITEM.items() if k != "phonetic_es"}
    with pytest.raises(ValidationError):
        GeneratedWordItem.model_validate(bad)


def test_invalid_cefr_level_rejected():
    bad = {**VALID_ITEM, "cefr_level": "C1"}  # out of A1-B2 range per spec
    with pytest.raises(ValidationError):
        GeneratedWordItem.model_validate(bad)


def test_hebrew_word_without_hebrew_script_rejected():
    """This is the guard against the model returning a transliteration or
    Latin text in the hebrew_word field instead of actual Hebrew script.
    """
    bad = {**VALID_ITEM, "hebrew_word": "chalon"}
    with pytest.raises(ValidationError):
        GeneratedWordItem.model_validate(bad)


def test_example_sentence_he_without_hebrew_script_rejected():
    bad = {**VALID_ITEM, "example_sentence_he": "Abro la ventana."}
    with pytest.raises(ValidationError):
        GeneratedWordItem.model_validate(bad)


def test_batch_with_one_malformed_item_rejected():
    bad_item = {**VALID_ITEM, "cefr_level": "Z9"}
    with pytest.raises(ValidationError):
        GeneratedWordBatch.model_validate({"words": [VALID_ITEM, bad_item]})


# ---------------------------------------------------------------------------
# Stage-2 verification schema (VerificationItem / VerificationBatch)
# ---------------------------------------------------------------------------


def test_verification_item_ok_status_passes():
    item = VerificationItem.model_validate({"index": 0, "status": "ok"})
    assert item.corrected is None
    assert item.note == ""


def test_verification_item_reject_status_passes():
    item = VerificationItem.model_validate(
        {"index": 3, "status": "reject", "note": "not a real word"}
    )
    assert item.corrected is None
    assert item.note == "not a real word"


def test_verification_item_corrected_status_requires_corrected_payload():
    with pytest.raises(ValidationError):
        VerificationItem.model_validate({"index": 0, "status": "corrected"})


def test_verification_item_corrected_status_with_payload_passes():
    item = VerificationItem.model_validate(
        {
            "index": 1,
            "status": "corrected",
            "corrected": VALID_ITEM,
            "note": "fixed phonetic_es stress mark",
        }
    )
    assert item.corrected is not None
    assert item.corrected.phonetic_es == "jalón"


def test_verification_item_ok_status_silently_drops_unexpected_corrected_payload():
    """Not an error — the model just isn't supposed to send `corrected`
    unless status is "corrected". We drop the unused payload rather than
    reject an otherwise-fine result (see the model_validator docstring)."""
    item = VerificationItem.model_validate(
        {"index": 0, "status": "ok", "corrected": VALID_ITEM}
    )
    assert item.corrected is None


def test_verification_item_invalid_status_rejected():
    with pytest.raises(ValidationError):
        VerificationItem.model_validate({"index": 0, "status": "maybe"})


def test_verification_batch_with_multiple_results_passes():
    batch = VerificationBatch.model_validate(
        {
            "results": [
                {"index": 0, "status": "ok"},
                {"index": 1, "status": "reject", "note": "bad translation"},
            ]
        }
    )
    assert len(batch.results) == 2
