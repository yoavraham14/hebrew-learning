"""Internal task-trigger endpoints — meant to be called by Cloud Scheduler,
never by the frontend or a real user. They exist because Cloud Run scales to
zero when idle, so the in-process APScheduler loop (services/scheduler.py)
that works fine for a long-lived local/VM process simply never fires on a
sleeping container. Cloud Scheduler wakes the service on a cron and hits
these instead — see DEPLOY.md for the `gcloud scheduler jobs create`
commands.

Auth is a shared secret, not the profile JWT — these aren't user identity
actions. Deliberately fails closed: if INTERNAL_TASK_SECRET isn't
configured, every request here is rejected, never silently open.
"""

import secrets

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import text

from app.config import get_settings
from app.deps import DbSession
from app.logging_config import get_logger
from app.services.scheduler import check_and_topup

logger = get_logger(__name__)

router = APIRouter(prefix="/internal/tasks", tags=["internal"])


def _require_task_secret(x_task_secret: str | None) -> None:
    settings = get_settings()
    configured = settings.internal_task_secret
    if not configured or not x_task_secret or not secrets.compare_digest(x_task_secret, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing task secret")


@router.post("/generate-topup")
def generate_topup(x_task_secret: str | None = Header(default=None)) -> dict:
    """Same logic the in-process scheduler used to call on a timer —
    check_and_topup() is already idempotent and already gated by the
    Gemini daily call cap, so triggering it externally on a cron changes
    nothing about its safety, only what wakes it up.
    """
    _require_task_secret(x_task_secret)
    check_and_topup()
    return {"status": "ok"}


@router.post("/db-keepalive")
def db_keepalive(db: DbSession, x_task_secret: str | None = Header(default=None)) -> dict:
    """Trivial SELECT 1 against Supabase — free-tier Supabase projects
    pause after a stretch of total inactivity, and this is the entire
    fix: touch the DB every few days so it never goes quiet long enough
    to trigger that.
    """
    _require_task_secret(x_task_secret)
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
