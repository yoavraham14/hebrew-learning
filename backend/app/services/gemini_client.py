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
from app.schemas import (
    GeneratedWordBatch,
    GeneratedWordItem,
    SentenceBackfillBatch,
    SentenceBackfillItem,
    SentenceBackfillResult,
    SentenceBackfillVerificationBatch,
    VerificationBatch,
)

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


# Shared between the generation prompt and the verification prompt so the
# two calls never drift apart on what "correct" phonetics means. Referenced
# by both _build_prompt and _build_verification_prompt.
_PHONETIC_RULES = """- Use SPANISH spelling conventions so a Spanish speaker reading it aloud
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
  "chalon" is fine there, if that's the closest English rendering)."""

# Applies _PHONETIC_RULES word-by-word across a whole sentence rather than
# a single word — shared between the generation and backfill prompts for
# example_sentence_phonetic_es, same reasoning as _PHONETIC_RULES itself.
_SENTENCE_PHONETIC_RULES = f"""{_PHONETIC_RULES}
- This applies to EVERY word in the sentence, not just the vocabulary word
  being taught — a Spanish reader with no Hebrew literacy should be able to
  read the whole transliterated sentence aloud and produce natural Hebrew.
  Use normal Spanish sentence spacing/punctuation; do not transliterate
  word-by-word in isolation and then concatenate without regard for how the
  sentence reads as a whole."""

# Bump this whenever _SENTENCE_SPECIFICITY_RULES changes in a way that
# could make a previously-accepted sentence fail now. WordPair.
# sentence_rules_version is stamped with this value at insert time
# (word_generator._insert_words_with_verification) and again whenever a
# sentence gets regenerated/backfilled (word_generator.
# run_sentence_backfill_batch, or the one-off manual backfill pass — see
# WordPair.sentence_source) — the backfill selection query is
# `sentence_rules_version < CURRENT_...`, so bumping this constant is what
# makes backfill reconsider every row again.
#
# History: v1 originally meant "blank is mid-sentence, disambiguated by
# context on both sides" (a reaction to a live "אני רוצה ___" sentence
# where every same-topic distractor still fit). That requirement is GONE
# as of this comment, superseded by a UI-level fix instead: fill_blank
# cards now show the full native-language sentence above the blanked
# target-language one (see exercise_ladder.build_multiple_choice_card's
# fill_blank_native_sentence), so the learner already knows the target
# concept before reading the target sentence — the sentence itself no
# longer has to be self-disambiguating. v1 is redefined below rather than
# bumped to v2 because nothing in production was ever actually processed
# under the old v1 meaning (confirmed: still 100% at v0 when this shipped).
CURRENT_SENTENCE_RULES_VERSION = 1

# Shared between the generation and verification prompts (and the sentence-
# backfill prompts, which face the identical problem) so what counts as an
# acceptable sentence means the same thing everywhere it's checked for.
#
# Deliberately NOT requiring the blank to be mid-sentence or the sentence
# to rule out same-topic distractors on its own — that used to be required
# here, but fill_blank cards now show the full native-language sentence
# above the blanked target-language one (see exercise_ladder.py), so the
# learner already knows the intended meaning before reading the target
# sentence. The target sentence's job is just to be a natural, correct
# example of the word in use — same bar as before v1 ever existed.
_SENTENCE_SPECIFICITY_RULES = """- The sentence must be natural, grammatically correct, and use the
  vocabulary word in its most common, everyday sense — not an obscure or
  overly literary usage. A bare subject+verb+object sentence (e.g. "אני
  אוכל ___" / "I eat ___") is perfectly fine; it does NOT need to rule out
  other same-topic words on its own, since the learner sees the full
  native-language translation of the sentence before the target-language
  one, which already tells them which word is intended."""


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
  This sentence is also used as a fill-in-the-blank exercise (the word
  gets blanked out), but the learner is shown the full native-language
  translation of the sentence first, so it does NOT need to be
  self-disambiguating on its own:
{_SENTENCE_SPECIFICITY_RULES}
- example_sentence_es: the Spanish translation of that same example sentence.

Then produce phonetic transliterations. Two for hebrew_word alone — one for
an English-reading learner (phonetic_en) and, MOST IMPORTANTLY, one for a
SPANISH-reading learner (phonetic_es) who cannot read Hebrew script and does
not read English phonetics naturally. Get phonetic_es right:

{_PHONETIC_RULES}

And one more, for the FULL example_sentence_he (not just the word) — a
Spanish-reading learner needs to be able to sound out the whole sentence,
not just the vocabulary word in isolation:

- example_sentence_phonetic_es: the Spanish-phonetic transliteration of the
  entire example_sentence_he sentence.
{_SENTENCE_PHONETIC_RULES}

Return every item even if some words repeat common roots — just make sure all
{batch_size} hebrew_word values are distinct from each other and from the
excluded list above."""


def _build_verification_prompt(*, items: list[GeneratedWordItem], topic: str, cefr_level: str) -> str:
    indexed = [
        {"index": i, **item.model_dump()}
        for i, item in enumerate(items)
    ]
    return f"""You are reviewing a batch of Hebrew<->Spanish<->English vocabulary
entries for a bilingual flashcard app, for QUALITY — not just correctness.
Do NOT just check against a generic translation tool's most common answer;
check for the MOST NATURAL, EVERYDAY equivalent a native speaker would
actually use in casual conversation.

For each entry below (topic "{topic}", CEFR level {cefr_level}), check:
1. Is the target translation (spanish_word, and the Hebrew side) the most
   natural everyday word, not an unnecessarily formal, rare, or literary
   alternative?
2. Does the register match between source and target — a casual/colloquial
   word should not map to a stiff/formal one, and vice versa?
3. Is phonetic_es a phonetically correct Spanish-reader spelling of
   hebrew_word, with guttural consonants and stress correctly rendered?
   {_PHONETIC_RULES}
   Also sanity-check phonetic_en the same way for an English reader.
4. Does the example sentence actually use the word in its most common,
   everyday sense, in a natural and grammatically correct way?
{_SENTENCE_SPECIFICITY_RULES}
   If it doesn't, this is a "corrected" case, not "ok" — rewrite
   example_sentence_he and example_sentence_es together (they must still
   translate each other), and update example_sentence_phonetic_es to
   match the rewritten sentence.
5. Is example_sentence_phonetic_es a phonetically correct Spanish-reader
   transliteration of the FULL example_sentence_he sentence (not just the
   vocabulary word)?
   {_SENTENCE_PHONETIC_RULES}

Entries (JSON array, each tagged with its "index"):
{json.dumps(indexed, ensure_ascii=False)}

For each entry, return exactly one result with the SAME "index":
- status "ok" if everything checks out as-is — leave "corrected" unset.
- status "corrected" if something needs fixing — include the FULL corrected
  entry (every field, not just the changed ones) in "corrected", and a
  short "note" explaining what you changed and why.
- status "reject" only if the entry is fundamentally unusable (e.g. wrong
  translation entirely, not a real word) and cannot be simply corrected —
  include a "note" explaining why; leave "corrected" unset.

Return exactly {len(items)} results, one per input index, covering every
index from 0 to {len(items) - 1} exactly once."""


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


def verify_word_batch(
    *, items: list[GeneratedWordItem], topic: str, cefr_level: str
) -> VerificationBatch:
    """Stage 2 of the generation pipeline (SPEC.md-adjacent — see the
    translation-verification feature): sends the stage-1 batch back to
    Gemini for a quality pass. Raises the same error types as
    generate_word_batch — the caller (word_generator.run_generation_batch)
    handles both call sites identically.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiGenerationError("GEMINI_API_KEY is not configured")
    if not items:
        return VerificationBatch(results=[])

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _build_verification_prompt(items=items, topic=topic, cefr_level=cefr_level)

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VerificationBatch,
                temperature=0.2,  # verification should be consistent, not creative
            ),
        )
    except Exception as exc:
        if _is_billing_error(exc):
            raise GeminiBillingError(str(exc)) from exc
        raise GeminiGenerationError(f"Gemini verification call failed: {exc}") from exc

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, VerificationBatch):
        batch = parsed
    else:
        text = getattr(response, "text", None)
        if not text:
            raise GeminiGenerationError("Gemini verification call returned no content")
        try:
            data = json.loads(text)
            batch = VerificationBatch.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise GeminiGenerationError(f"invalid JSON/schema from verification call: {exc}") from exc

    indices = sorted(r.index for r in batch.results)
    if indices != list(range(len(items))):
        raise GeminiGenerationError(
            f"verification response index mismatch: expected 0..{len(items) - 1}, got {indices}"
        )
    return batch


# ---------------------------------------------------------------------------
# Sentence backfill pipeline (app.services.word_generator.
# run_sentence_backfill_batch) — for existing WordPair rows missing
# example_sentence_phonetic_es. Never re-translates hebrew_word/
# spanish_word/etc., which are already verified. Correlates by
# word_pair_id (a backfill batch spans arbitrary existing words of mixed
# topic/level, unlike a fresh generation batch which is always one
# topic/level), not array index.
#
# PRESERVES the existing sentence by default — only adds the phonetic
# transliteration. This mirrors the one-off manual backfill pass (see
# WordPair.sentence_source): existing sentences are already
# Gemini-generated and were already verified once, and the specificity
# requirement that used to justify rewriting them (see
# CURRENT_SENTENCE_RULES_VERSION's docstring) no longer applies. Only
# rewrite a sentence if it's actually defective — doesn't use the word,
# wrong grammar, wrong register — not as a matter of course.
# ---------------------------------------------------------------------------


def _build_sentence_backfill_prompt(items: list[SentenceBackfillItem]) -> str:
    indexed = [item.model_dump() for item in items]
    return f"""You are adding phonetic transliterations to existing example sentences in
a Hebrew<->Spanish<->English vocabulary bank (a bilingual flashcard app).
The translations AND example sentences below are already correct and
verified — do NOT change hebrew_word, spanish_word, english_word,
part_of_speech, topic, cefr_level, example_sentence_he, or
example_sentence_es, UNLESS an entry's example_sentence_he is actually
defective (doesn't use hebrew_word, wrong grammar, wrong register) — only
in that case, rewrite example_sentence_he and example_sentence_es together
(they must still translate each other). The bar for the sentence, if you
do need to touch it:
{_SENTENCE_SPECIFICITY_RULES}

For each entry, produce:
- example_sentence_he: normally just echo the input value back unchanged.
- example_sentence_es: normally just echo the input value back unchanged.
- example_sentence_phonetic_es: the Spanish-phonetic transliteration of the
  ENTIRE example_sentence_he sentence (not just the word) — this is the
  actual point of this pass:
{_SENTENCE_PHONETIC_RULES}

Entries (JSON array, each tagged with its "word_pair_id" — echo that same
id back in your result for each entry, do not reorder or drop any):
{json.dumps(indexed, ensure_ascii=False)}

Return exactly {len(items)} results, one per input word_pair_id, covering
every word_pair_id in the input exactly once."""


def regenerate_sentence_batch(items: list[SentenceBackfillItem]) -> SentenceBackfillBatch:
    """Stage 1 of the sentence-backfill pipeline. Same call/error shape as
    generate_word_batch — the caller (word_generator.
    run_sentence_backfill_batch) handles both call sites identically.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiGenerationError("GEMINI_API_KEY is not configured")
    if not items:
        return SentenceBackfillBatch(results=[])

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _build_sentence_backfill_prompt(items)

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SentenceBackfillBatch,
                temperature=0.9,
            ),
        )
    except Exception as exc:
        if _is_billing_error(exc):
            raise GeminiBillingError(str(exc)) from exc
        raise GeminiGenerationError(f"Gemini sentence-backfill call failed: {exc}") from exc

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, SentenceBackfillBatch):
        batch = parsed
    else:
        text = getattr(response, "text", None)
        if not text:
            raise GeminiGenerationError("Gemini sentence-backfill call returned no content")
        try:
            data = json.loads(text)
            batch = SentenceBackfillBatch.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise GeminiGenerationError(f"invalid JSON/schema from sentence-backfill call: {exc}") from exc

    ids = sorted(r.word_pair_id for r in batch.results)
    expected = sorted(item.word_pair_id for item in items)
    if ids != expected:
        raise GeminiGenerationError(
            f"sentence-backfill response id mismatch: expected {expected}, got {ids}"
        )
    return batch


def _build_sentence_backfill_verification_prompt(
    items: list[SentenceBackfillItem], results: list[SentenceBackfillResult]
) -> str:
    items_by_id = {item.word_pair_id: item for item in items}
    entries = [
        {
            "word_pair_id": r.word_pair_id,
            "hebrew_word": items_by_id[r.word_pair_id].hebrew_word,
            "spanish_word": items_by_id[r.word_pair_id].spanish_word,
            "topic": items_by_id[r.word_pair_id].topic,
            "cefr_level": items_by_id[r.word_pair_id].cefr_level,
            "example_sentence_he": r.example_sentence_he,
            "example_sentence_es": r.example_sentence_es,
            "example_sentence_phonetic_es": r.example_sentence_phonetic_es,
        }
        for r in results
    ]
    return f"""You are reviewing phonetic transliterations added to existing example
sentences in a Hebrew<->Spanish<->English vocabulary bank (a bilingual
flashcard app). Each entry below carries its own topic and CEFR level
(this batch spans multiple words, not one shared topic). The example
sentences themselves are normally UNCHANGED from what already existed —
only reject/correct them if something is actually wrong, don't rewrite a
fine sentence just to make it "better." For each entry, check:

1. Is the example sentence natural, grammatically correct, and does it
   actually use hebrew_word in its common everyday sense?
{_SENTENCE_SPECIFICITY_RULES}
   Only if it fails this (not just "could be more specific") is this a
   "corrected" case — rewrite example_sentence_he and example_sentence_es
   together (they must still translate each other), and update
   example_sentence_phonetic_es to match.
2. Is example_sentence_phonetic_es a phonetically correct Spanish-reader
   transliteration of the FULL example_sentence_he sentence?
   {_SENTENCE_PHONETIC_RULES}

Entries (JSON array, each tagged with its "word_pair_id"):
{json.dumps(entries, ensure_ascii=False)}

For each entry, return exactly one result with the SAME "word_pair_id":
- status "ok" if everything checks out as-is — leave "corrected" unset.
- status "corrected" if something needs fixing — include the FULL corrected
  sentence trio (example_sentence_he, example_sentence_es,
  example_sentence_phonetic_es, and the same word_pair_id) in "corrected",
  and a short "note" explaining what you changed.
- status "reject" only if you cannot produce a usable sentence for this
  word at all — include a "note" explaining why; leave "corrected" unset.

Return exactly {len(results)} results, one per input word_pair_id, covering
every word_pair_id in the input exactly once."""


def verify_sentence_backfill_batch(
    items: list[SentenceBackfillItem], results: list[SentenceBackfillResult]
) -> SentenceBackfillVerificationBatch:
    """Stage 2 of the sentence-backfill pipeline. Same call/error/id-
    matching shape as verify_word_batch — the caller (word_generator.
    run_sentence_backfill_batch) handles both call sites identically.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiGenerationError("GEMINI_API_KEY is not configured")
    if not results:
        return SentenceBackfillVerificationBatch(results=[])

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _build_sentence_backfill_verification_prompt(items, results)

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SentenceBackfillVerificationBatch,
                temperature=0.2,
            ),
        )
    except Exception as exc:
        if _is_billing_error(exc):
            raise GeminiBillingError(str(exc)) from exc
        raise GeminiGenerationError(f"Gemini sentence-backfill verification call failed: {exc}") from exc

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, SentenceBackfillVerificationBatch):
        batch = parsed
    else:
        text = getattr(response, "text", None)
        if not text:
            raise GeminiGenerationError("Gemini sentence-backfill verification call returned no content")
        try:
            data = json.loads(text)
            batch = SentenceBackfillVerificationBatch.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise GeminiGenerationError(f"invalid JSON/schema from sentence-backfill verification call: {exc}") from exc

    ids = sorted(r.word_pair_id for r in batch.results)
    expected = sorted(r.word_pair_id for r in results)
    if ids != expected:
        raise GeminiGenerationError(
            f"sentence-backfill verification response id mismatch: expected {expected}, got {ids}"
        )
    return batch
