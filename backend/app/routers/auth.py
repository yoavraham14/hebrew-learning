from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DbSession
from app.models import Profile
from app.schemas import LoginRequest, TokenResponse
from app.security import create_access_token, verify_pin

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    profile = db.scalar(select(Profile).where(Profile.slug == payload.profile_slug))

    # Constant-shape response whether the slug is unknown or the PIN is
    # wrong — don't let the error message reveal which one it was.
    if profile is None or not verify_pin(payload.pin, profile.pin_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid profile or PIN")

    token = create_access_token(profile.id, profile.slug)
    return TokenResponse(access_token=token, profile=profile)
