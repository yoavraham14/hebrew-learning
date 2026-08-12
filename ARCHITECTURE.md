# Architecture

Reference doc for how Lingua is actually built, as of the exercise-ladder +
review-games + Hebrew-audio work. Written for future you (or future Claude)
picking this up cold — especially for planning deployment, since none exists
yet (see [Deployment](#deployment---not-built-yet) at the bottom). For *what*
the product does and *why* each decision was made, see [SPEC.md](SPEC.md) —
this doc is *how it's actually wired together* in the code as it stands
today, which has drifted ahead of SPEC.md in a few places (noted inline).

---

## 1. System overview

```
┌─────────────────┐         ┌──────────────────────────┐        ┌────────────┐
│   Browser        │  HTTPS  │  FastAPI backend          │  SQL   │  Postgres  │
│  React + Vite     │◄───────►│  (stateless, one process) │◄──────►│            │
│  (localhost:5173) │  JSON   │  (localhost:8000)         │        │            │
└─────────────────┘         └───────────┬──────────────┘        └────────────┘
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
                   │ Gemini API  │ │ gTTS         │ │ APScheduler │
                   │ (word gen,  │ │ (unofficial, │ │ (in-process │
                   │ free tier,  │ │ Hebrew audio,│ │ background  │
                   │ hard cap)   │ │ no API key)  │ │ thread)     │
                   └─────────────┘ └─────────────┘ └─────────────┘
```

- **Backend is 100% stateless** — every piece of durable state lives in
  Postgres (word bank, per-user progress, generation call log, cached audio
  bytes). This was a deliberate v1 decision so the backend can be
  horizontally scaled or moved into a container/k8s pod later with zero code
  changes (see `/health`, `/ready`, structured stdout logging — all already
  container-friendly).
- **Frontend never talks to Gemini or gTTS directly** — it only ever talks to
  the FastAPI backend. All external-service calls are backend-only, which is
  also where the cost-safety firewall lives.
- **Two fixed users, no public signup.** Auth is PIN + JWT, not a real
  accounts system (see [§5](#5-auth)).

---

## 2. Repository layout

```
lingua-app/
  SPEC.md              — product spec (what/why)
  ARCHITECTURE.md       — this file (how)
  DEPLOY.md              — exact Cloud Run + Supabase deploy commands (see §10)
  README.md               — local dev setup, step by step
  Dockerfile                — production image: build frontend, then FastAPI serves both (see §10)
  .dockerignore               — keeps .env/.venv/node_modules out of the build context/image
  docker-compose.yml            — Postgres ONLY, for local dev (see §8)

  backend/
    app/
      main.py            — FastAPI app, lifespan (bootstrap + scheduler), CORS, static/SPA serving, router mounting
      config.py           — Settings (pydantic-settings), all env vars, one lru_cache'd instance
      db.py               — SQLAlchemy engine/session, get_db() dependency
      deps.py             — CurrentProfile (JWT auth dep), DbSession
      security.py          — bcrypt PIN hashing, JWT encode/decode
      models.py            — SQLAlchemy ORM models (source of truth for schema)
      schemas.py            — Pydantic request/response + LLM-output validation schemas
      logging_config.py     — structured JSON logs to stdout

      routers/             — thin HTTP layer, one file per resource
        auth.py               POST /api/auth/login
        profiles.py            GET /api/profiles
        cards.py                GET /api/cards/next, POST /{id}/rate, POST /{id}/answer
        progress.py              GET /api/progress
        audio.py                  GET /api/audio/word-pairs/{id}
        health.py                  GET /health, GET /ready
        internal.py                 POST /internal/tasks/{generate-topup,db-keepalive} — Cloud Scheduler only, see §10

      services/             — all real logic lives here, routers just call in
        word_generator.py       orchestrates the 2-stage Gemini generation pipeline + cost firewall
        gemini_client.py         raw Gemini API calls (generate + verify), billing-error detection
        cards.py                  card selection, rate_word/answer_word, ties review ladder + exercise ladder together
        exercise_ladder.py        5-level exercise system: level transitions, card building, distractor selection
        review_games.py            recovery/mixed round triggers and construction
        review.py                   pure box/interval scheduling logic (SM-2-shaped, not full SM-2 yet)
        streak.py                    pure daily-streak logic
        progress.py                   words_seen/words_known/streak aggregation for GET /progress
        audio.py                       gTTS wrapper, niqqud stripping
        scheduler.py                    APScheduler: bootstrap-if-empty + periodic top-up job

      scripts/
        seed_profiles.py          one-time/idempotent: creates or rotates PIN for the two fixed profiles
        clear_generation_halt.py    manually clears the Gemini billing-halt kill-switch

    alembic/versions/         — see §4 for what each migration added
    tests/                       — 84 tests, pytest, in-memory SQLite (no Postgres needed)

  frontend/
    src/
      types.ts                — TypeScript types mirroring backend schemas.py exactly
      api/client.ts             — typed fetch wrapper, the ONLY place that calls the backend
      hooks/useAuth.ts           — token/profile session state (localStorage-backed)
      App.tsx                     — top-level: ProfilePicker vs. authenticated shell (nav + streak badge)
      pages/
        ProfilePicker.tsx           pick profile -> enter PIN -> login
        StudyPage.tsx                 orchestrates the continuous deck + round state machine (§6.3)
        ProgressPage.tsx               words_seen/known/streak display
      components/
        StudyCard.tsx                dispatcher across all 5 exercise shapes
        RevealExercise.tsx            level 0 (reveal-and-self-rate)
        MultipleChoiceExercise.tsx     levels 1-4 (all multiple-choice), shared answer/feedback flow
        ExerciseOptionGrid.tsx          the 4-option tap grid, phonetic-pairing enforcement lives here
        CardHeader.tsx                   shared topic/CEFR/review-badge header
        RoundBanner.tsx                   "bonus round" announcement before recovery/mixed rounds
        AudioButton.tsx                    plays cached backend audio (Hebrew) or speechSynthesis (fallback/Spanish)
        RatingButtons.tsx                   knew_it/almost/didnt_know (level 0 only)
        StreakBadge.tsx                       nav streak flame
      lib/text.ts               — isHebrewText() — RTL detection for option text
```

---

## 3. Data model

All tables in `app/models.py`; Alembic migrations are the only thing that
should ever touch the real schema (never hand-edit Postgres).

```
Profile ──┐
          │ 1:N
          ▼
UserWordProgress ──N:1── WordPair
          │
          │ (profile_id, word_pair_id also referenced by)
          ▼
RecentMiss ──N:1── WordPair

GenerationCallLog   (independent — audit trail for the Gemini cost cap)
GenerationStatus     (independent — single-row kill-switch state, id=1)
```

| Table | Purpose | Notable columns |
|---|---|---|
| `profiles` | The two fixed users. This row IS the identity. | `native_lang`/`target_lang` (direction is data, never hardcoded), `pin_hash`, `current_streak`, `total_reviews` (drives review-game triggers) |
| `word_pairs` | Shared bidirectional word bank (Hebrew–Spanish–English triple). | `phonetic_en`/`phonetic_es` (both always stored), `verified`/`verification_note` (stage-2 pipeline result), `hebrew_audio` (cached gTTS MP3 bytes, nullable) |
| `user_word_progress` | Per-(profile, word) state. Two *independent* ladders live on this one row. | `box`/`repetitions`/`ease_factor`/`interval_days`/`next_review_at` (review-interval ladder, §6.1) — `exercise_level`/`exercise_level_streak` (difficulty ladder, §6.2) |
| `recent_miss` | Pool a recovery round draws from; rows deleted once served. | `missed_at` |
| `generation_call_log` | One row per Gemini call (or pair of calls — generate+verify). | `api_calls_made` (1 or 2 — both count against the daily cap) |
| `generation_status` | Single row (id=1). The billing kill-switch. | `halted`, `halted_reason` — once true, nothing clears it except a human running `clear_generation_halt.py` |

**Migration history** (`backend/alembic/versions/`):

| Revision | Added |
|---|---|
| `0001_initial` | Base schema: profiles, word_pairs, user_word_progress, generation_call_log, generation_status |
| `0002_verification` | `word_pairs.verified`/`verification_note`, `generation_call_log.api_calls_made`/`verify_status`/`words_verified_ok` |
| `0003_exercise_ladder` | `user_word_progress.exercise_level`/`exercise_level_streak`, `profiles.total_reviews`, `recent_miss` table |
| `0004_hebrew_audio` | `word_pairs.hebrew_audio` (bytea) |

---

## 4. Word generation pipeline (two-stage, cost-firewalled)

Entry point: `word_generator.run_generation_batch(db)`, called from three
places — startup bootstrap (bank empty), the periodic top-up job, and
nowhere else. **This function is the only thing allowed to call Gemini** —
that's a deliberate chokepoint so the cost firewall can't be bypassed by a
new call site forgetting to check the cap.

```
run_generation_batch()
  │
  ├─ 1. halted? ──yes──► return 0 (never calls Gemini)
  ├─ 2. daily_count >= cap? ──yes──► return 0
  │
  ├─ 3. STAGE 1: generate_word_batch()  [1 Gemini call]
  │      → Pydantic-validated GeneratedWordBatch
  │      → on GeminiBillingError: halt permanently, log, return 0
  │      → on GeminiGenerationError: log, return 0 (retried next cycle)
  │
  ├─ 4. cap check again (stage 1 already used one call)
  │
  ├─ 5. STAGE 2: verify_word_batch()  [1 more Gemini call, if cap allows]
  │      → LLM re-reviews the batch for naturalness/register/phonetic accuracy
  │      → per-item: "ok" | "corrected" | "reject"
  │      → on error/skip: stage-1 words still get inserted, just unverified
  │
  └─ 6. insert every item regardless of verification outcome
         verified=True/False + verification_note set accordingly
         dedup via DB UNIQUE(hebrew_word, spanish_word) + pre-check
         only verified=True words are ever served as NEW material
         (see cards.py get_next_card) — unverified ones just sit in the bank
```

**Cost firewall specifics** (`GEMINI_DAILY_CALL_CAP`, default 200):
`GenerationCallLog.api_calls_made` is summed per-day, not row-counted,
because one batch run can make up to 2 real calls. `GeminiBillingError` is
deliberately broad — it fires on HTTP 402, HTTP 429 `RESOURCE_EXHAUSTED`
(yes, even though that's technically a generic rate-limit code — see the
docstring in `gemini_client.py` for why), or any message mentioning
billing/credit/prepay/payment. Once halted, **nothing automatically
clears it** — `python -m app.scripts.clear_generation_halt` is the only way,
and it prints the reason first without `--yes` so you can sanity-check
before clearing.

---

## 5. Auth

No signup, two fixed PIN-protected profiles.

```
POST /api/auth/login {profile_slug, pin}
  → bcrypt.checkpw against profiles.pin_hash
  → 401 for wrong PIN AND unknown slug (same response shape — doesn't
    leak which one was wrong)
  → on success: JWT {sub: profile_id, slug, iat, exp}, HS256, 90-day expiry
  → frontend stores it in localStorage (useAuth.ts), sends as
    `Authorization: Bearer <token>` on every request (api/client.ts)
```

`CurrentProfile` (`deps.py`) decodes the JWT and loads the `Profile` row on
every authenticated request — no session table, no refresh flow. Re-login
after expiry is an accepted UX tradeoff at this scale (two users).

PINs are provisioned by `python -m app.scripts.seed_profiles`, reading
`HEBREW_LEARNER_PIN`/`SPANISH_LEARNER_PIN` from the environment once — never
committed, never logged. Re-running the script rotates the PIN if the env
var changed.

`GET /api/audio/word-pairs/{id}` and `GET /api/profiles` are the only two
**unauthenticated** endpoints — audio because plain `<audio src>` tags can't
attach an `Authorization` header, profiles because the picker needs the list
before login exists.

---

## 6. Study flow

### 6.1 Review-interval ladder (`services/review.py`) — *when* a word resurfaces

Pure, DB-free function: `compute_next_state(current_box, current_repetitions,
current_ease_factor, result, now) -> LadderResult`.

- `knew_it` → box advances (capped), interval from `LADDER_DAYS = [1, 3, 7,
  14, 30, 60, 120]`
- `almost` → box unchanged, 1-day interval
- `didnt_know` → box resets to 0, resurfaces in 10 minutes (same session)

`repetitions`/`ease_factor` are populated but not yet used to compute
intervals — the schema is SM-2-shaped on purpose so a real SM-2
implementation can replace just this one function later, no migration
needed.

### 6.2 Exercise difficulty ladder (`services/exercise_ladder.py`) — *how* a word is tested

Independent of the box ladder, stored on the same `user_word_progress` row
(`exercise_level` 0-4, `exercise_level_streak`).

| Level | `exercise_type` | Shown as |
|---|---|---|
| 0 | `reveal` | today's original passive card (self-rated via `RatingButtons`) |
| 1 | `multiple_choice` | native prompt → pick correct target from 4 options |
| 2 | `reverse` | target prompt (+ audio + phonetic) → pick correct native meaning |
| 3 | `audio_only` | no visible prompt, only audio → pick correct meaning |
| 4 | `fill_blank` | example sentence with target word blanked → pick correct word |

`compute_level_transition(current_level, current_streak, correct)`: one miss
demotes a level (floor 0); `PROMOTE_STREAK = 2` consecutive correct answers
promotes one level (ceiling 4). Levels 1-4 answers go through
`POST /api/cards/{id}/answer` (objectively checked: `selected_word_pair_id
== word_pair_id`); level 0 uses the existing `/rate` self-rating, where
`correct` is defined as `result == "knew_it"` for level-transition purposes
(mirrors `LadderResult.correct`).

**The "never require raw Hebrew script" constraint is structural, not a
convention**: `exercise_ladder._text_and_phonetic(profile, word_pair, lang)`
is the *only* place that decides whether a phonetic accompanies a piece of
Hebrew text — it does, whenever `lang == "he" and profile.native_lang !=
"he"`. Every prompt and every option in every exercise type routes through
this one function. The frontend (`ExerciseOptionGrid.tsx`) never has to make
this decision itself — it just never suppresses a phonetic that's present.

Distractors (`_pick_distractors`): same topic + CEFR level as the correct
answer when the pool allows it, falling back to any other verified word if
too thin. Never includes unverified words.

### 6.3 Review games (`services/review_games.py`)

Keyed off `Profile.total_reviews` (incremented on every `/rate` or `/answer`
call, regardless of exercise type):

- **Recovery round** — every 15th review. Pulls up to 5 `RecentMiss` rows
  for that profile, deletes them once served (a miss is only ever offered
  once).
- **Mixed round** — every 100th review. Pulls up to 8 due/near-due
  `UserWordProgress` rows, broader refresher, nothing consumed.
- Mixed wins on coincidence (e.g. review #300).

Delivered as a `round_due` field on the `RateResponse`/`AnswerResponse` of
the review that triggered it — not a separate endpoint. Round cards are
always plain `multiple_choice`, regardless of the word's own stored
`exercise_level` (supplementary practice, not level-progression).
**Frontend decision:** a round triggered *while already mid-round* is
ignored, not queued — rounds don't nest (`StudyPage.tsx`'s
`maybeStartRound`).

### 6.4 Card selection (`services/cards.py`)

`get_next_card`: due review (soonest `next_review_at`) → else an unseen
**verified** word → else fall back to soonest-upcoming review (keeps the
continuous deck from ever dead-ending). Both `rate_word` and `answer_word`
share one tail (`_apply_result`): box ladder, exercise-level transition,
`RecentMiss` logging on a miss, streak update, `total_reviews` increment,
review-game check.

---

## 7. Hebrew pronunciation audio (`services/audio.py`)

**Why this exists at all:** the obvious approach — browser
`speechSynthesis` — depends on a Hebrew voice being installed on the
*listener's device*, and many devices (confirmed: this dev machine) simply
don't have one. Fails silently, no error, no fallback possible from the
frontend alone.

**Current implementation:** `gTTS`, an unofficial Python wrapper around
Google Translate's own "listen" feature (the same endpoint the speaker icon
on translate.google.com calls). No API key, no billing account — same
zero-cost-risk posture as the Gemini side, but **no SLA**: it's a
reverse-engineered endpoint Google could change or block without warning.
(An earlier iteration used eSpeak NG — offline, zero network dependency,
but robotic-sounding; swapped out for voice quality. See git history if
you ever need to revert for reliability reasons.)

```
GET /api/audio/word-pairs/{id}   [UNAUTHENTICATED — see §5]
  │
  ├─ word_pairs.hebrew_audio already cached? → serve it, Cache-Control: immutable
  │
  └─ not cached:
       ├─ strip niqqud (vowel points) — gTTS handles it fine either way,
       │  this is defensive; the PRIOR eSpeak implementation needed this
       │  as an actual bug fix (niqqud made it ramble 8x longer)
       ├─ gTTS synthesis (real network call, ~1-2s)
       ├─ on failure of ANY kind → HTTP 404, never 500
       └─ on success → cache in word_pairs.hebrew_audio, serve
```

**Frontend fallback chain** (`AudioButton.tsx`'s `playPronunciation`): for
Hebrew with a known `word_pair_id`, try the cached backend audio; on
`Audio.play()` rejection OR an `error` event, fall back to
`speechSynthesis`. Spanish never uses this path at all — Latin-script
browser TTS voices are near-universal, so it stays on `speechSynthesis`
directly, unchanged from before this feature existed.

**Two real bugs worth knowing about if audio ever breaks again** (both
caught live during this build, both have regression tests in
`tests/test_audio.py`):
1. Passing Hebrew text as an inline CLI arg to a Windows-run TTS binary
   gets mangled by the console codepage before the process sees it —
   always read text from a UTF-8 file/stdin on Windows, never argv, if you
   ever shell out to another TTS binary.
2. A stale dev-server process from an earlier session silently squatted on
   the expected port and served old code while every `curl` health-check
   against "the right port" looked fine — always check for a port-owner
   PID mismatch before trusting that a running server reflects current
   code.

---

## 8. Local dev (current state)

```
docker compose up -d          # Postgres only, localhost:5432
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev     # Vite, localhost:5173
```

Backend and frontend run **natively**, not in Docker — only Postgres is
containerized. Full env var reference: `.env.example` (root, backend) and
`frontend/.env.example`. Full step-by-step: [README.md](README.md).

**Config is 100% environment variables** (`app/config.py`,
`pydantic-settings`) — no hardcoded secrets, no hardcoded URLs beyond local
dev defaults. This was intentionally built for containerization from day
one even though no container exists yet.

---

## 9. Testing

84 backend tests (`pytest`, `backend/tests/`), all against an in-memory
SQLite DB via `conftest.py` fixtures — **no Postgres needed to run the
suite**. Covers: LLM-output schema validation, the verification pipeline
(mocked Gemini calls), the review-interval ladder (pure function, exhaustive
boundary cases), the exercise ladder (level transitions, distractor
selection, phonetic-pairing invariants), review games (trigger boundaries,
recovery-pool consumption), audio (mocked router tests + live-network tests
that self-skip if gTTS is unreachable), and full API integration flows
(login → card → rate/answer → progress).

No frontend test suite exists yet (`tsc --noEmit` + `vite build` are the
only current frontend correctness gates). Worth adding before this gets much
bigger — Vitest + React Testing Library would be the natural fit given the
Vite setup already in place.

---

## 10. Deployment

**Target: Google Cloud Run + Supabase (managed Postgres).** Full step-by-step
commands live in [DEPLOY.md](DEPLOY.md) — this section is the *why*/*how it
fits together*, not the runbook.

### Shape of it

One container, built by the root `Dockerfile` (multi-stage: `node:20-alpine`
builds the React frontend, `python:3.12-slim` runs FastAPI and serves the
built frontend as static files from the same process). No nginx/Caddy in
front of it — Cloud Run terminates TLS and handles routing itself. Postgres
is Supabase, entirely external to Cloud Run; `DATABASE_URL` just points at
it (Transaction pooler, port `6543`, for the app's runtime traffic — see
below for why migrations use the Session pooler instead).

```
Browser ──HTTPS──► Cloud Run (single container: FastAPI + static React)
                         │
                         ├──SQL (pooler, :6543)──► Supabase Postgres
                         │
                         ├──HTTPS──► Gemini API (word generation)
                         └──HTTPS──► gTTS (Hebrew audio)

Cloud Scheduler ──HTTPS + shared secret──► Cloud Run:
    every 2h    → POST /internal/tasks/generate-topup
    every 3 days → POST /internal/tasks/db-keepalive
```

### Same-container frontend serving (`app/main.py`)

`STATIC_DIR` (`/app/static` inside the container — absent in local dev, so
none of this activates there) holds the built `dist/`. API routers are
registered first; a catch-all `GET /{full_path:path}` registered **last**
returns `index.html` for anything not already claimed, so client-side
routes survive a hard refresh. `/assets` is mounted as `StaticFiles`
separately, matching Vite's build output shape. The frontend is built with
`VITE_API_URL=""` (empty, not unset) so `api/client.ts`/`AudioButton.tsx`
issue relative `/api/...` requests — same-origin, no CORS involved in
production at all.

### Why the in-process scheduler had to go (`app/routers/internal.py`)

`services/scheduler.py`'s APScheduler loop works fine for a long-lived
process but **cannot work on Cloud Run**: the container scales to zero when
idle, and a sleeping process can't run a timer. `ENABLE_IN_PROCESS_SCHEDULER
=false` in the Cloud Run env disables it entirely; Cloud Scheduler wakes the
service on a cron and hits two new endpoints instead:

- `POST /internal/tasks/generate-topup` — same `check_and_topup()` the
  scheduler used to call, unchanged, still cap-gated. Cadence: every 2
  hours (relaxed from the in-process default of 15 minutes — no need to
  wake a scale-to-zero service that often for a word-bank buffer check).
- `POST /internal/tasks/db-keepalive` — trivial `SELECT 1`, every 3 days,
  to stay under Supabase free tier's inactivity auto-pause window.

Both are protected by a shared secret (`INTERNAL_TASK_SECRET`) compared via
`secrets.compare_digest` against an `X-Task-Secret` header — **fails
closed**: unset secret means every request is rejected, never accidentally
open. This is app-level auth, not the profile JWT — Cloud Scheduler isn't a
user.

### Migrations: Session pooler, neither Direct nor Transaction pooler

`alembic upgrade head` is run manually from a developer machine, against
Supabase's **Session pooler** (port `5432`, via the pooler hostname) —
deliberately neither of the other two options:

- Not the **Direct connection** (`db.<project-ref>.supabase.co`) — it's
  IPv6-only unless you've bought Supabase's IPv4 add-on, and confirmed live
  to fail outright (DNS resolution error) on any network without an
  outbound IPv6 route. Common enough to not be a fringe case.
- Not the **Transaction pooler** (`6543`, what the running app uses) —
  PgBouncer's transaction-mode pooling doesn't support the session-level
  features (prepared statements, multi-statement DDL) Alembic needs.

Never baked into container startup either way: Cloud Run can start multiple
instances around the same time, and racing migrations across instances is
worth avoiding entirely rather than handling.

### What's still a real gap, not yet solved

- The Cloud Scheduler shared secret is visible in plaintext to anyone with
  read access to the job config in the GCP console — acceptable for now
  (matches what was explicitly asked for), but `--oidc-service-account-email`
  auth would remove the app-level secret entirely if this ever needs
  hardening.
- The Gemini cost firewall (§4) is app-level only — it stops the *app* from
  overcalling, but doesn't touch the GCP/Google AI Studio project's own
  billing settings. Worth an independent check of the actual project's
  billing state before pointing a real deployment at it.
- No frontend test suite, no CI pipeline running tests/build before deploy
  — `DEPLOY.md`'s steps are entirely manual right now.
