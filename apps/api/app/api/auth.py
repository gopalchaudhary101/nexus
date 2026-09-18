from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.memory import wipe_user_memory
from ..audit.service import log as audit_log
from ..core.config import get_settings
from ..core.errors import ApiError, RateLimited
from ..core.security import auth_limiter_factory, create_token, hash_password, verify_password
from ..db.models import User
from ..db.session import get_db
from ..schemas import DeleteMeIn, LoginIn, RegisterIn, TokenOut, UserOut
from .deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _check_rate_limit(request: Request) -> None:
    limiter = auth_limiter_factory()
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(ip):
        raise RateLimited("Too many authentication attempts. Try again in a minute.")


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    _check_rate_limit(request)
    existing = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing is not None:
        raise ApiError("An account with this email already exists", code="exists")
    user = User(email=body.email, name=body.name,
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_log(db, user.id, "auth.register", actor="user", target=user.email)
    s = get_settings()
    return TokenOut(access_token=create_token(user.id, s.secret_key, s.jwt_ttl_hours),
                    user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    _check_rate_limit(request)
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiError("Invalid email or password", code="bad_credentials")
    audit_log(db, user.id, "auth.login", actor="user", target=user.email)
    s = get_settings()
    return TokenOut(access_token=create_token(user.id, s.secret_key, s.jwt_ttl_hours),
                    user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserOut.model_validate(user)


@router.delete("/me", status_code=204)
def delete_me(body: DeleteMeIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise ApiError("Password does not match", code="bad_credentials")
    wipe_user_memory(db, user.id)
    audit_log(db, user.id, "account.deleted", actor="user", target=user.email)
    db.delete(user)  # cascades to all user data
    db.commit()
    return None
