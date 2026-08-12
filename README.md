# Lingua — Bilingual Vocabulary Trainer

A daily flashcard app for two people learning each other's language: a
Hebrew speaker learning Spanish, and a Spanish speaker learning Hebrew.
Words are generated at runtime by Gemini (free tier only — see
[SPEC.md](./SPEC.md) §2 for the cost-safety design), stored in Postgres,
and served instantly from that bank.

Full product spec: [SPEC.md](./SPEC.md). How it's built: [ARCHITECTURE.md](./ARCHITECTURE.md).
Deploying it: [DEPLOY.md](./DEPLOY.md).

## Stack

- **Backend:** FastAPI, SQLAlchemy 2.0, Alembic, Postgres
- **Frontend:** React + Vite + Tailwind
- **Word generation:** Google Gemini API (free tier), with a hard daily call
  cap and a kill-switch on any billing-related error

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (for local Postgres)
- A free Gemini API key from <https://aistudio.google.com/apikey>
- **Hebrew audio** generates server-side (`gTTS`, installed via
  `requirements.txt` — no separate setup) so pronunciation plays identically
  on every device, instead of relying on each browser/OS having a Hebrew
  text-to-speech voice installed (many don't). No API key, no billing
  account. It IS an unofficial, undocumented Google Translate endpoint
  though — no SLA, could change or get blocked without warning. If it's
  ever unavailable, the app still works: the frontend silently falls back
  to the browser's own `speechSynthesis`, exactly like before this feature
  existed.

## 1. Start Postgres

```sh
docker compose up -d
```

This starts Postgres only, on `localhost:5432`, with a persistent volume.
Backend and frontend run natively (not in Docker) for fast hot reload.

## 2. Backend setup

```sh
cd backend
python -m venv .venv

# Windows (Git Bash):
source .venv/Scripts/activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt

cp ../.env.example .env
```

Edit `backend/.env`:

- `GEMINI_API_KEY` — your free-tier key.
- `JWT_SECRET` — any long random string (e.g. `openssl rand -hex 32`).
- `HEBREW_LEARNER_PIN` / `SPANISH_LEARNER_PIN` — pick two PINs, one per
  profile. These are only read once by the seed script below.
- Leave `DATABASE_URL` as-is if you're using the default `docker compose`
  Postgres.

Run migrations:

```sh
alembic upgrade head
```

Seed the two profiles (creates them if missing, rotates the PIN if you
re-run it with a new value):

```sh
python -m app.scripts.seed_profiles
```

Start the API:

```sh
uvicorn app.main:app --reload --port 8000
```

On first startup, if the word bank is empty, the backend automatically
generates an initial batch of words from Gemini (well within the free
tier). Check `http://localhost:8000/ready` — it reports DB connectivity and
the generation pipeline's status (daily call count vs. cap, whether it's
halted, last successful generation).

## 3. Frontend setup

In a second terminal:

```sh
cd frontend
npm install
cp .env.example .env   # VITE_API_URL defaults to http://localhost:8000
npm run dev
```

Open `http://localhost:5173`. Pick a profile, enter its PIN, and start
studying.

## Running tests

```sh
cd backend
source .venv/Scripts/activate   # if not already active
pytest
```

Covers: LLM-output schema validation (valid + malformed cases), the
review-interval ladder logic, and a full API integration test (login → fetch
card → rate → progress updates), all against an in-memory SQLite DB — no
Postgres needed to run the suite.

## Project layout

```
backend/
  app/
    routers/       — FastAPI route handlers (auth, profiles, cards, progress, health)
    services/       — business logic: card selection, review ladder, streaks,
                       Gemini client, word-bank generation, scheduler
    scripts/        — one-off scripts (profile PIN seeding)
    models.py        — SQLAlchemy models
    schemas.py       — Pydantic request/response + LLM-output validation schemas
    config.py         — all configuration, read from environment variables
  alembic/          — DB migrations
  tests/
frontend/
  src/
    pages/          — ProfilePicker, StudyPage, ProgressPage
    components/      — StudyCard (the reveal flow), AudioButton, RatingButtons, StreakBadge
    api/client.ts    — typed fetch wrapper
    hooks/useAuth.ts — token/profile session state
docker-compose.yml  — Postgres only, for local dev
SPEC.md             — the full product spec
```

## Operational notes

- **Cost safety:** the backend will never call Gemini more than
  `GEMINI_DAILY_CALL_CAP` times per day (default 200, far above what this
  app actually needs), and if Gemini ever returns a billing-related error
  (including a plain `429 RESOURCE_EXHAUSTED` — see the note below),
  generation halts entirely until you clear it manually — it never retries,
  never upgrades, never touches Cloud Billing itself. Check `/ready` if
  words stop refreshing; `generation.halted` and `generation.halted_reason`
  tell you why. Once you've confirmed in Google AI Studio / Cloud Console
  that the underlying issue is actually resolved, clear the halt with:
  ```sh
  python -m app.scripts.clear_generation_halt --yes
  ```
  (Run it once without `--yes` first — it prints the halt reason and does
  nothing, so you can double-check before clearing.)
  - **Why `RESOURCE_EXHAUSTED` (429) counts as billing-related here:** at
    this app's tiny call volume, hitting Gemini's rate limit at all is
    anomalous, and in practice Google's 429 message can itself reference
    depleted prepayment credits / billing — so it's treated as a halt
    condition rather than a silent retry loop. See
    `app/services/gemini_client.py` for the exact detection logic.
- **No accounts beyond the two fixed profiles.** PINs are provisioned via
  `app.scripts.seed_profiles`, not a signup flow — see SPEC.md §3.
- **Stateless backend, ready for containers/k8s later:** all state lives in
  Postgres; config is 100% environment variables; `/health` and `/ready`
  are already there. Nothing in this repo builds the actual container/k8s
  deployment — that's intentionally out of scope for now.
