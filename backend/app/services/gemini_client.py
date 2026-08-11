"""Thin wrapper around the Gemini API. All cost-control policy (daily cap,
halting) lives in word_generator.py — this module only knows how to make one
generation call and turn the result into a validated GeneratedWordBatch, or
raise a typed error the caller can act on.
"""

import json

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.config import get_settings
from app.logging_config import get_logger
from app.schemas import GeneratedWordBatch

logger = get_logger(__name__)


class GeminiGenerationError(Exception):
    """A generation call failed for an ordinary (transient/retryable) reason
    — bad JSON, validation failure, timeout, plain rate limit, etc. The
    caller should log it and try again on the next scheduled cycle; it does
    NOT indicate any risk of a charge.
    """


class GeminiBillingError(Exception):
    """The API response indicates continuing would require, may have
    triggered, or is otherwise entangled with billing/payment — HTTP 402,
    HTTP 429 RESOURCE_EXHAUSTED, or any message mentioning billing/credits/
    payment. This is the signal that halts generation entirely until a
    human investigates (SPEC.md §2.1).

    RESOURCE_EXHAUSTED is deliberately included even though it's Google's
    generic "quota" code, not a dedicated "billing" code: at this app's tiny
    call volume (bootstrap + occasional top-up, nowhere near the free-tier
    RPM/RPD ceiling under normal operation), hitting it at all is anomalous
    and worth a human look rather than a silent retry loop — and in
    practice Google's own RESOURCE_EXHAUSTED message for this project
    explicitly referenced depleted prepayment credits and a billing
    console link, i.e. it *was* a billing-adjacent error wearing a generic
    code. Given the hard "never cause a charge" requirement, false-halt
    (safe, just needs a manual look) is the correct failure direction —
    never false-continue.
    """


# Broad on purpose — see the RESOURCE_EXHAUSTED note above. A false halt
# costs a manual `/ready` check; a false continue risks exactly what this
# firewall exists to prevent.
_BILLING_KEYWORDS = ("billing", "credit", "prepay", "payment")


def _is_billing_error(exc: Exception) -> bool:
    status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status_code in (402, 429):
        return True
    status_name = str(getattr(exc, "status", "") or "").upper()
    if status_name == "RESOURCE_EXHAUSTED":
        return True
    message = str(exc).lower()
    return any(keyword in message for keyword in _BILLING_KEYWORDS)


def _build_prompt(*, topic: str, cefr_level: str, exclude_hebrew_words: list[str], batch_size: int) -> str:
    exclusion_block = ""
    if exclude_hebrew_words:
        exclusion_block = (
            "Do not reuse any of these Hebrew words (already in the bank):\n"
            + ", ".join(exclude_hebrew_words)
            + "\n\n"
        )

    return f"""You are generating vocabulary data for a bilingual Hebrew<->Spanish
flashcard app, bridged through English. Generate exactly {batch_size} DISTINCT
vocabulary words at CEFR level {cefr_level}, on the topic "{topic}".

{exclusion_block}For each word, produce:
- hebrew_word: the word written in Hebrew script (with niqqud/vowel points if it
  helps disambiguate pronunciation).
- english_word: the English translation (bridge language).
- spanish_word: the Spanish translation.
- part_of_speech: one of noun, verb, adjective, adverb, phrase, etc.
- cefr_level: "{cefr_level}"
- topic: "{topic}"
- example_sentence_he: one short, natural sentence in Hebrew using the word.
- example_sentence_es: the Spanish translation of that same example sentence.

Then produce TWO phonetic transliterations of hebrew_word — one for an
English-reading learner (phonetic_en) and, MOST IMPORTANTLY, one for a
SPANISH-reading learner (phonetic_es) who cannot read Hebrew script and does
not read English phonetics naturally. Get phonetic_es right:

- Use SPANISH spelling conventions so a Spanish speaker reading it aloud
  produces the correct Hebrew sound. Example: the Hebrew word for "window"
  (חלון) should be written "jalón" in phonetic_es — Spanish "j" is close to
  the Hebrew guttural sound ח. Do NOT write "chalon"; Spanish "ch" (as in
  "chico") is the wrong sound entirely.
- Hebrew ר (resh) is a guttural/uvular sound, closer to a French R than a
  Spanish tap-R or English R. Never render it as a bare unmarked "r" — use a
  double letter, an accent, or another cue a Spanish reader will notice as
  unusual, e.g. "rr" or a diacritic, consistently.
- Mark the stressed syllable explicitly, e.g. with an acute accent on the
  stressed vowel (áéíóú) following normal Spanish stress-marking
  conventions. Hebrew very often stresses the final syllable, which Spanish
  speakers will default to NOT doing — so mark it whenever it's not where
  Spanish stress rules would predict.
- phonetic_en can use standard English-reader phonetic conventions (e.g.
  "chalon" is fine there, if that's the closest English rendering).

Return every item even if some words repeat common roots — just make sure all
{batch_size} hebrew_word values are distinct from each other and from the
excluded list above."""


def generate_word_batch(
    *, topic: str, cefr_level: str, exclude_hebrew_words: list[str], batch_size: int
) -> GeneratedWordBatch:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiGenerationError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _build_prompt(
        topic=topic,
        cefr_level=cefr_level,
        exclude_hebrew_words=exclude_hebrew_words,
        batch_size=batch_size,
    )

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeneratedWordBatch,
                temperature=0.9,
            ),
        )
    except Exception as exc:  # google-genai raises several exception types across versions
        if _is_billing_error(exc):
            raise GeminiBillingError(str(exc)) from exc
        raise GeminiGenerationError(f"Gemini call failed: {exc}") from exc

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, GeneratedWordBatch):
        return parsed

    text = getattr(response, "text", None)
    if not text:
        raise GeminiGenerationError("Gemini returned no content")

    try:
        data = json.loads(text)
        return GeneratedWordBatch.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise GeminiGenerationError(f"invalid JSON/schema from Gemini: {exc}") from exc
