import pytest
from pydantic import ValidationError

from app.schemas import GeneratedWordBatch, GeneratedWordItem

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
