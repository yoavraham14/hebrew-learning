"""One-time (or re-run-to-rotate) provisioning of the two fixed profiles.

Run with:  python -m app.scripts.seed_profiles

Reads HEBREW_LEARNER_PIN and SPANISH_LEARNER_PIN from the environment (see
.env.example) and creates or updates the two Profile rows. Safe to re-run —
re-running with a new PIN value rotates that profile's PIN. Never logs the
PIN itself, only whether a profile was created or updated.
"""

import sys

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.logging_config import configure_logging, get_logger
from app.models import Profile
from app.security import hash_pin

logger = get_logger(__name__)

PROFILE_DEFINITIONS = [
    {
        "slug": "hebrew_learner",
        "display_name": "Hebrew Learner",
        "native_lang": "es",
        "target_lang": "he",
        "pin_attr": "hebrew_learner_pin",
    },
    {
        "slug": "spanish_learner",
        "display_name": "Spanish Learner",
        "native_lang": "he",
        "target_lang": "es",
        "pin_attr": "spanish_learner_pin",
    },
]


def main() -> int:
    configure_logging()
    settings = get_settings()
    db = SessionLocal()
    try:
        missing = [
            d["pin_attr"] for d in PROFILE_DEFINITIONS if not getattr(settings, d["pin_attr"])
        ]
        if missing:
            logger.error(
                "missing required PIN environment variable(s) — see .env.example",
                extra={"extra_fields": {"missing": missing}},
            )
            return 1

        for definition in PROFILE_DEFINITIONS:
            pin = getattr(settings, definition["pin_attr"])
            pin_hash = hash_pin(pin)

            existing = db.scalar(select(Profile).where(Profile.slug == definition["slug"]))
            if existing is None:
                db.add(
                    Profile(
                        slug=definition["slug"],
                        display_name=definition["display_name"],
                        native_lang=definition["native_lang"],
                        target_lang=definition["target_lang"],
                        pin_hash=pin_hash,
                    )
                )
                logger.info("created profile", extra={"extra_fields": {"slug": definition["slug"]}})
            else:
                existing.pin_hash = pin_hash
                logger.info(
                    "updated profile PIN", extra={"extra_fields": {"slug": definition["slug"]}}
                )

        db.commit()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
