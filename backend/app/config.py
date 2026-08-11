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

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
