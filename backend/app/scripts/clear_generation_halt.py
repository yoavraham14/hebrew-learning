"""Manually clear the generation kill-switch after investigating a halted
billing-related error (SPEC.md §2.1). This is deliberately the *only* way
to resume generation — the app itself never auto-clears this, never
retries past it, and never touches billing on its own.

Run with:  python -m app.scripts.clear_generation_halt

Prints the halt reason it's about to clear before doing so, and requires
--yes to actually clear it (dry-run by default) so this doesn't get run
absent-mindedly.
"""

import sys

from app.db import SessionLocal
from app.logging_config import configure_logging, get_logger
from app.services.word_generator import get_or_create_status

logger = get_logger(__name__)


def main() -> int:
    configure_logging()
    confirm = "--yes" in sys.argv

    db = SessionLocal()
    try:
        status = get_or_create_status(db)
        if not status.halted:
            print("Generation is not currently halted — nothing to do.")
            return 0

        print("Generation is currently HALTED.")
        print(f"  Halted at:  {status.halted_at}")
        print(f"  Reason:     {status.halted_reason}")
        print()

        if not confirm:
            print("This was dry-run only. Re-run with --yes to clear the halt:")
            print("  python -m app.scripts.clear_generation_halt --yes")
            print()
            print("Only do this once you've confirmed (in Google AI Studio / Cloud")
            print("Console) that the underlying billing/quota issue is actually")
            print("resolved — this script does not check that for you.")
            return 0

        status.halted = False
        status.halted_reason = None
        status.halted_at = None
        db.commit()
        logger.info("generation halt cleared manually")
        print("Cleared. Generation will resume on the next scheduled top-up check.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
