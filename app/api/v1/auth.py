from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.services.audit import record

router = APIRouter()


def _issue(user: User, db: Session) -> TokenResponse:
    settings = get_settings()
    token = create_access_token(user.email, {"uid": user.id, "role": user.role.value, "org": user.organization_id})
    user.last_login_at = datetime.now(timezone.utc)
    record(db, organization_id=user.organization_id, user_id=user.id, action="login", entity_type="user", entity_id=str(user.id))
    db.commit()
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
    )


@router.post("/login", response_model=TokenResponse)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return _issue(user, db)


@router.post("/token", response_model=TokenResponse)
def login_json(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return _issue(user, db)


@router.post("/demo", response_model=TokenResponse)
def demo_login(db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.allow_demo_login:
        raise HTTPException(404, "Demo login disabled")
    user = db.scalar(select(User).where(User.email == settings.default_admin_email))
    if not user:
        raise HTTPException(404, "Demo user missing")
    return _issue(user, db)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
