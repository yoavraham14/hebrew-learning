# Bilingual Vocabulary Trainer — SPEC

Status: **Draft — awaiting "spec approved"**
Last updated: 2026-08-11

## 0. Who this is for

Two real users, daily use on phones:

- **You** — native Hebrew speaker, learning Spanish.
- **Your girlfriend** (Peru) — native Spanish speaker, learning Hebrew. She **cannot
  read the Hebrew alphabet**. Every Hebrew word must be paired with audio and a
  Spanish-phonetic transliteration she can actually read and say correctly.

This is a real product, not a demo. Mobile-first, fast, and it has to feel good
to open for five minutes a day.

---

## 1. Core learning model

The app shows a word in the learner's **native** language and reveals the
translation in the **target** language, bridged through English.

```
Profile "Hebrew learner" (Spanish native, learning Hebrew)
  Prompt:  Spanish word            e.g. "qué"
  Reveal:  English "what"
           Hebrew script "מה"
           Pronunciation "ma" (written in SPANISH-reader phonetics)

Profile "Spanish learner" (Hebrew native, learning Spanish)
  Prompt:  Hebrew word              e.g. "לרקוד"
  Reveal:  English "dance"
           Spanish "bailar"
```

`direction` (native → target) is a field on the profile, never hardcoded, so a
future third profile or a flipped direction doesn't require touching card/reveal
logic.

### 1.1 Transliteration — the part that must not be wrong

The Hebrew pronunciation line is written **for a Spanish reader**, not an
English one, because that's the only reader who needs it (Hebrew script itself
carries pronunciation for the Hebrew-native learner, so this field only matters
in the "Hebrew learner" profile).

- `חלון` (window): write **"jalón"**, not "chalon" — Spanish `j` is the correct
  guttural-ish sound; Spanish `ch` (as in "chico") is wrong.
- `ר` is guttural/uvular, closer to a French R than an English/Spanish tap —
  never render it as a bare "r" with no cue (e.g. use a diacritic or note).
- Mark the stressed syllable explicitly (e.g. capitalize it, or add an accent
  mark) — Hebrew often stresses the final syllable, and Spanish speakers will
  default to the second-to-last by habit.

**Data model stores both**, always, regardless of which profile is active:

- `phonetic_en` — English-reader-style transliteration
- `phonetic_es` — Spanish-reader-style transliteration (the one that matters
  for real use in v1, since Hebrew is only ever the target-with-script side)

The UI displays only the transliteration matching the **learner's native
language** for that profile.

---

## 2. Word generation pipeline

**No hardcoded word list.** Words are generated at runtime by an LLM, stored in
Postgres as a shared word bank, and the UI only ever reads from the bank — it
never waits on a live generation call.

### 2.1 Model & provider — Gemini Flash, free tier, hard cost firewall

- Provider: **Google Gemini API**, current-generation **Flash** model (not
  Flash-Lite, not Pro — Pro is paid-only). The exact model ID string is
  confirmed against `ai.google.dev/gemini-api/docs/pricing` **at build time**
  (not pinned in this spec, since it may have shifted).
- Structured JSON output via Gemini's response-schema / JSON mode.
- Free-tier limits to respect (Flash, subject to change — re-check at build
  time): ~15 requests/minute, ~250 requests/day. The app only needs 15–25
  calls for the initial bank, so this is comfortable headroom, not a real
  constraint — but the app must never silently exceed it either.

**Absolute hard requirement: this app must never cause a charge.**

- A daily Gemini call counter is tracked in Postgres (date + count).
- A hard cap, `GEMINI_DAILY_CALL_CAP` (env var, default **200**), is checked
  before every generation call. On reaching the cap: **stop calling Gemini for
  the rest of that day and serve existing bank words only.** Never block the
  user-facing UI, never retry, never fall back to any paid provider.
- The app **never** touches Google Cloud Billing settings, programmatically or
  otherwise, under any circumstance.
- If Gemini ever returns a billing-related error (e.g. quota-exceeded-with-
  billing-prompt, or any error indicating the free tier was exhausted and a
  paid tier would be required), the backend **immediately stops all
  generation calls**, logs it clearly (structured log, `level=error`), and
  surfaces it on `/ready` or `/health` (see §7) so it's visible without
  digging through logs.
- Raising the cap or enabling billing is **your decision alone**, made
  manually outside the app. The app never prompts for it, never suggests it
  in-product, never automates it.

### 2.2 Shared bidirectional word bank

Both profiles read from **one shared table of word pairs** — a "word pair" is
a Hebrew–Spanish–English triple with metadata, independent of which profile is
studying it. This means:

- Half the generation calls compared to two independent pipelines.
- You and your girlfriend end up learning overlapping vocabulary.
- Per-profile state (seen/known/review interval) is tracked **separately**,
  in a per-user-per-word progress table — the word content is shared, the
  learning progress is not.

### 2.3 Batching, validation, dedup

- Generate in batches of **20–30 words** per Gemini call.
- Each generated item includes: source word, English translation, target
  translation, target script (Hebrew, when applicable), `phonetic_en`,
  `phonetic_es`, part of speech, CEFR level (A1–B2), topic, one short example
  sentence in **both** languages.
- Vary topic and CEFR level across batches (rotate through a fixed topic list
  and CEFR ladder) so vocabulary stays broad rather than clustering.
- Every response is validated against a **Pydantic v2 schema** before
  touching the database. Malformed items are rejected and the batch is
  retried (bounded retries, e.g. 2) — never inserted unvalidated.
- Pass the list of already-generated Hebrew source words as an exclusion list
  in the prompt, to reduce repeats (best-effort, not a hard guarantee).
- **Unique constraint** on (`hebrew_word`, `spanish_word`) at the DB level as
  the actual dedup backstop, with `ON CONFLICT DO NOTHING` on insert.

### 2.4 Bootstrap & top-up

- **Bootstrap:** on first backend startup, if the word bank is empty, the
  backend automatically generates one initial batch. No manual seeding step.
- **Top-up:** an in-process periodic task (e.g. APScheduler running inside the
  FastAPI process — no external scheduler infra needed) wakes on an interval
  (`TOPUP_CHECK_INTERVAL_MINUTES`, default 15) and checks, per profile
  direction, how many **unseen** words remain. If below
  `TOPUP_THRESHOLD` (env var, default **20**), it triggers one top-up batch —
  still gated by the daily cap in §2.1.
- This design carries over cleanly to a container running in AWS later — no
  code changes needed, just making sure the process stays alive.

---

## 3. Identity & auth

No public signup. Two fixed profiles, each protected by a PIN.

1. On load, the user picks a profile: **"Hebrew learner"** or **"Spanish
   learner"**.
2. They enter that profile's PIN.
3. Backend validates the PIN (hashed with bcrypt, never stored in plaintext),
   issues a JWT scoped to that `profile_id`, long-lived (e.g. 90 days).
4. Frontend stores the JWT in `localStorage` and sends it as `Authorization:
   Bearer <token>` on every request. No refresh-token flow needed at this
   scale — re-entering the PIN after expiry is fine.
5. The two profile PINs are provisioned via a one-time seed script reading
   from environment variables (`HEBREW_LEARNER_PIN`, `SPANISH_LEARNER_PIN`) —
   never committed, never logged.

This is intentionally not a general accounts system — it's the minimum that
lets progress persist reliably per person without building signup, password
reset, email verification, etc. `profile_id` is the identity used everywhere
progress, review queues, and streaks are tracked.

---

## 4. Study flow

- **Continuous deck**, no fixed daily session boundary. Cards keep coming
  until the user closes the app — due reviews are prioritized over new words,
  mixed in as capacity allows (exact ratio is an implementation detail tuned
  during build, not a hard spec requirement).
- Card flow: show prompt word → tap/click to reveal (translation, script,
  transliteration, example sentences) → self-rate **Knew it / Almost /
  Didn't know** → next card.
- Reveal is an animated transition (e.g. flip or fade+scale), not an instant
  DOM swap.

### 4.1 Review scheduling

v1 uses a simple interval ladder keyed off the three self-rating buttons, but
the schema is shaped so full SM-2 can be dropped in later without a migration:

- `user_word_progress` stores: `box` (int, simple-ladder position),
  `repetitions`, `ease_factor`, `interval_days`, `next_review_at`,
  `last_result` (`knew_it` | `almost` | `didnt_know`), `times_seen`,
  `times_correct`.
- v1 ladder logic (illustrative, tuned during build):
  - **Didn't know** → box resets to 0, `next_review_at` = now + a few minutes
    (resurfaces same session).
  - **Almost** → box stays, short interval (e.g. next day).
  - **Knew it** → box advances, interval grows (e.g. 1d → 3d → 7d → 14d → …).
- `ease_factor` and `repetitions` are populated but not yet used to compute
  intervals in v1 — they exist purely so SM-2 can be swapped in as the
  interval function later, reading state that's already there.

---

## 5. Progress view

Per profile: words seen, words known (reached some "known" threshold box),
current daily streak. Simple counts/queries against `user_word_progress`, no
separate analytics pipeline.

---

## 6. Audio

- Browser **Web Speech API** (`speechSynthesis`), voices `he-IL` and `es-ES`
  depending on which side is being spoken.
- No fallback/detection for missing voices in v1 (explicitly out of scope per
  your call) — the play button just calls the API; if a voice is missing on a
  given device, nothing audible happens. Revisit if it turns out to be a real
  problem in practice.

---

## 7. Config, health, logging

- All config via environment variables. `.env.example` documents every
  variable with no real values; `.env` is gitignored.
- Backend is stateless — all state in Postgres.
- `GET /health` — liveness only (process is up).
- `GET /ready` — checks DB connectivity **and** surfaces generation-pipeline
  status: last successful Gemini call, current daily call count vs cap, and
  whether generation is currently halted due to a billing-related error
  (§2.1).
- Structured JSON logs to stdout, no log files.

---

## 8. UI / mobile / design

- **Web app only** (no native app — see §10) — a normal responsive website,
  reachable and fully usable from **both** iPhone Safari and desktop
  browsers. Not "mobile app with a desktop afterthought" — just one site that
  adapts its layout to whatever screen it's opened on (e.g. a centered,
  constrained-width card on wide viewports rather than a stretched-out
  layout; full-width on phones).
- **Interface language is English** for both profiles (buttons, labels,
  settings, error messages) — only the studied *content* (prompt word,
  reveal, example sentences) switches language per profile. This keeps the
  UI simple and avoids a second localization surface.
- Hebrew strings render with `dir="rtl"` scoped to just that string/element
  (e.g. the script line), never on the whole page.
- Font: **Noto Sans Hebrew** or **Heebo**, loaded explicitly (no silent
  fallback to a default system font for Hebrew text).
- Deliberate color palette + font pairing, applied consistently — no default
  Tailwind blue, no system font stack for Latin text either.
- The studied word is the visual focus: large, high-contrast, well-typed.
- Reveal uses a smooth transition (CSS transform/opacity), not an instant
  swap.

---

## 9. Stack

- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic.
- **DB:** PostgreSQL.
- **Frontend:** React + Vite + Tailwind.
- **Local dev:** `docker compose` for Postgres only; backend and frontend run
  natively with hot reload (uvicorn `--reload`, Vite dev server).
- **LLM:** Google Gemini API (`google-generativeai` / `google-genai` Python
  SDK), current-gen Flash model, free tier only (§2.1).

---

## 10. Out of scope for v1

Accounts beyond the two fixed PIN-protected profiles, social features,
images, offline mode, native app, TTS voice-availability detection, AWS
deployment/containerization (must not be *blocked*, but not built now).

---

## 11. Deliverables

1. `SPEC.md` (this file).
2. Working backend + frontend, runnable locally via `docker compose up`
   (Postgres) + `uvicorn` + `vite dev`.
3. Alembic migrations for the full schema (word_pairs, user_word_progress,
   profiles, gemini_call_log or similar).
4. `README.md` a stranger could follow end-to-end (env setup, running
   migrations, seeding profile PINs, starting both dev servers).
5. Tests:
   - Gemini output → Pydantic schema validation (valid + malformed cases).
   - Review-interval ladder logic (all three rating paths, box transitions).
   - One API integration test (e.g. fetch-next-card → rate → progress
     updates, against a test DB).

---

## Open items resolved during interview (for reference)

| Question | Decision |
|---|---|
| User identity | Fixed PIN-protected profile = identity (`profile_id`), simple JWT auth |
| Word bank sharing | One shared bidirectional word-pair pool for both profiles |
| TTS fallback | Skipped for v1 — no detection/warning |
| Session structure | Continuous deck, no fixed daily session size |
| Generation model | Google Gemini Flash (free tier), **not** Anthropic — hard cost firewall, never touches billing |
| Bootstrap | Auto-generate on first backend startup if bank is empty |
| Top-up trigger | In-process periodic check (no external scheduler) |
| UI language | English throughout, regardless of profile |
