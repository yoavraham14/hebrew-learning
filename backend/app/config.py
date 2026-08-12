"""All configuration comes from environment variables. See .env.example
at the repo root for the full documented list — nothing here has a
hardcoded secret or a hardcoded URL/port other than sane local-dev defaults.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg://lingua:lingua@localhost:5432/lingua"

    # --- Auth ---
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_days: int = 90

    # Seed-only PINs, read once by scripts/seed_profiles.py. Never logged.
    hebrew_learner_pin: str | None = None
    spanish_learner_pin: str | None = None

    # --- CORS ---
    # Comma-separated list of allowed origins for the frontend dev/prod server.
    cors_origins: str = "http://localhost:5173"

    # --- Gemini generation pipeline ---
    gemini_api_key: str | None = None
    # Verify against ai.google.dev/gemini-api/docs/pricing before deploying —
    # model IDs and free-tier availability shift over time. Confirmed current
    # GA (non-preview, non-Lite) Flash model as of this build.
    gemini_model: str = "gemini-3.6-flash"

    # Hard, non-negotiable cost firewall (see SPEC.md §2.1). The app must
    # never be able to cause a charge without the operator raising this cap
    # manually.
    gemini_daily_call_cap: int = 200

    generation_batch_size: int = 25
    topup_threshold: int = 20
    topup_check_interval_minutes: int = 15

    # In-process APScheduler top-up loop (§2.4). Fine for local dev / a
    # long-lived process, but useless on Cloud Run: the container scales to
    # zero when idle and the scheduler simply doesn't fire while asleep.
    # Cloud Run deploys set this False and rely on Cloud Scheduler hitting
    # POST /internal/tasks/generate-topup instead — see app/routers/internal.py.
    enable_in_process_scheduler: bool = True

    # Shared-secret auth for the /internal/tasks/* endpoints (Cloud
    # Scheduler triggers, not user-facing — see app/routers/internal.py).
    # None means those endpoints reject everything — fails closed, never
    # accidentally open. Set only in the Cloud Run deployment's env.
    internal_task_secret: str | None = None

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
