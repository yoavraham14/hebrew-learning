from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.deps import DbSession
from app.services.word_generator import get_generation_health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness only — the process is up. No DB check on purpose, so a
    transient DB blip doesn't get the pod killed by a liveness probe.
    """
    return {"status": "ok"}


@router.get("/ready")
def ready(db: DbSession, response: Response) -> dict:
    """Readiness — checks DB connectivity and surfaces the generation
    pipeline's cost-firewall state (SPEC.md §2.1 / §7), so a halted
    generator is visible without digging through logs.
    """
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    generation = get_generation_health(db)

    ok = db_ok and not generation["halted"]
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if ok else "error",
        "database": {"connected": db_ok},
        "generation": generation,
    }
