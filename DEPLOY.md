# Deploying to Cloud Run + Supabase

One container (built by the root `Dockerfile`) serves both the API and the
built React frontend. Postgres is Supabase, external to Cloud Run entirely.
The in-process top-up scheduler is replaced by Cloud Scheduler hitting two
shared-secret-protected endpoints — see [ARCHITECTURE.md §10](ARCHITECTURE.md#10-deployment)
for why (Cloud Run scales to zero; an in-process timer can't fire on a
sleeping container).

Region: **`us-east1`** throughout, to sit next to Supabase's
`aws-0-us-east-1` pooler and stay inside Cloud Run's free-tier-eligible
regions — worth a quick re-check against the current Cloud Run pricing page
before your first deploy, the same way this repo already tells you to
re-verify the Gemini model ID (things like this shift over time).

Every command below is for **you** to run — none of this touches your GCP
project from here.

---

## 0. One-time setup

```sh
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories create lingua \
  --repository-format=docker --location=us-east1
```

## 1. Secrets

Never put real values in this repo or in chat — generate/paste them
directly into `gcloud`:

```sh
# The Supabase POOLER string (port 6543, sslmode=require) — the one you'll
# provide. See .env.example's DATABASE_URL comment for the exact shape.
echo -n "postgresql+psycopg://postgres.<ref>:<password>@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require" | \
  gcloud secrets create DATABASE_URL --data-file=-

echo -n "$(openssl rand -hex 32)" | gcloud secrets create JWT_SECRET --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create INTERNAL_TASK_SECRET --data-file=-
echo -n "YOUR_GEMINI_API_KEY"      | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "YOUR_HEBREW_LEARNER_PIN"  | gcloud secrets create HEBREW_LEARNER_PIN --data-file=-
echo -n "YOUR_SPANISH_LEARNER_PIN" | gcloud secrets create SPANISH_LEARNER_PIN --data-file=-
```

## 2. Run migrations against Supabase (one time, and after every future migration)

**Use the Session pooler (port `5432`, via the pooler hostname), not the
Direct connection and not the Transaction pooler (`6543`), for this:**

- The **Direct connection** (`db.<project-ref>.supabase.co`) is IPv6-only
  unless you've bought Supabase's IPv4 add-on — confirmed live: it fails
  with a DNS resolution error on any network without an outbound IPv6
  route, which is common (this is a known, frequently-hit Supabase gotcha,
  not a one-off).
- The **Transaction pooler** (`6543`, what the deployed app uses at
  runtime — see `.env.example`) doesn't suit Alembic: PgBouncer's
  transaction-mode pooling doesn't support the session-level features
  (prepared statements, multi-statement DDL transactions) migrations need.
- The **Session pooler** is the one that actually works for this: same
  pooler hostname as the transaction pooler, same IPv4 compatibility, but
  port `5432` and PgBouncer in session mode — behaves like a real direct
  connection for Alembic's purposes without the IPv6 requirement.

Run from your own machine, not inside the deployed container:

```sh
cd backend
DATABASE_URL="postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require" \
  alembic upgrade head

# One-time also: seed the two profile PINs (same session-pooler connection)
DATABASE_URL="postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require" \
  HEBREW_LEARNER_PIN=... SPANISH_LEARNER_PIN=... \
  python -m app.scripts.seed_profiles
```

Note the username shape difference from the direct connection: it's
`postgres.<project-ref>` (matching the transaction pooler's convention),
not plain `postgres`.

## 3. Build and push the image

```sh
gcloud builds submit --tag us-east1-docker.pkg.dev/YOUR_PROJECT_ID/lingua/backend:latest .
```

(Run from the repo root — the Dockerfile's `COPY` paths are root-relative.)

## 4. Deploy

```sh
gcloud run deploy lingua \
  --image us-east1-docker.pkg.dev/YOUR_PROJECT_ID/lingua/backend:latest \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars CORS_ORIGINS=http://localhost:5173,GEMINI_MODEL=gemini-3.6-flash,GEMINI_DAILY_CALL_CAP=200,GENERATION_BATCH_SIZE=25,TOPUP_THRESHOLD=20,ENABLE_IN_PROCESS_SCHEDULER=false,LOG_LEVEL=INFO \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,INTERNAL_TASK_SECRET=INTERNAL_TASK_SECRET:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest,HEBREW_LEARNER_PIN=HEBREW_LEARNER_PIN:latest,SPANISH_LEARNER_PIN=SPANISH_LEARNER_PIN:latest
```

No `--port` flag — Cloud Run injects `PORT` and the container already reads
it (`CMD uvicorn ... --port ${PORT}` in the Dockerfile). No
`--min-instances` — default scale-to-zero, matching this app's whole
cost-conscious design.

**After this first deploy**, note the printed Service URL
(`https://lingua-xxxxx-ue.a.run.app`-shaped) and update `CORS_ORIGINS` to
that value with a redeploy or `gcloud run services update lingua
--update-env-vars CORS_ORIGINS=<url>` — same-origin requests don't actually
need it (frontend and API are served from the same container/origin now),
but it's the correct value for defense in depth and for any future
split-origin use.

## 5. Cloud Scheduler jobs

Replace `YOUR_INTERNAL_TASK_SECRET` with the real value you generated in
step 1, and `SERVICE_URL` with the URL from step 4.

```sh
# Top-up check, every 2 hours — relaxed from the in-process default of 15
# minutes; the word-bank buffer doesn't need waking that often, and every
# invocation cold-starts a scaled-to-zero service.
gcloud scheduler jobs create http lingua-topup \
  --location us-east1 \
  --schedule "0 */2 * * *" \
  --uri "SERVICE_URL/internal/tasks/generate-topup" \
  --http-method POST \
  --headers "X-Task-Secret=YOUR_INTERNAL_TASK_SECRET"

# DB keepalive, every 3 days — safely under Supabase free tier's ~7-day
# inactivity auto-pause window.
gcloud scheduler jobs create http lingua-db-keepalive \
  --location us-east1 \
  --schedule "0 0 */3 * *" \
  --uri "SERVICE_URL/internal/tasks/db-keepalive" \
  --http-method POST \
  --headers "X-Task-Secret=YOUR_INTERNAL_TASK_SECRET"
```

**Known tradeoff, not fixed here:** the shared secret is visible in
plaintext to anyone with read access to these job configs in the GCP
console/`gcloud scheduler jobs describe` — matches what you asked for
(shared-secret header, not OIDC), just worth knowing. A stronger version
later would use `--oidc-service-account-email` instead and drop the header
entirely, verified by Cloud Run's own IAM rather than an app-level secret.

## 6. Verify

```sh
curl https://SERVICE_URL/health
curl https://SERVICE_URL/ready
curl -X POST https://SERVICE_URL/internal/tasks/db-keepalive -H "X-Task-Secret: YOUR_INTERNAL_TASK_SECRET"
```

Then open `https://SERVICE_URL/` in a browser — same container should serve
the app itself, not just the API.

## Future deploys (after the first)

Just steps 2 (if there's a new migration), 3, and 4 — secrets and scheduler
jobs are one-time setup.
