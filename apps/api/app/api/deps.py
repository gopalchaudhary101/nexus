"""Shared dependencies: JWT auth + rate limiting."""
from __future__ import annotations

import jwt as pyjwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import Unauthorized
from ..core.security import RateLimiter, decode_token
from ..db.models import User
from ..db.session import get_db


def auth_limiter() -> RateLimiter:
    return RateLimiter(max_requests=get_settings().auth_rate_limit)


def get_current_user(authorization: str = Header(default=""),
                     db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized("Missing Bearer token")
    token = authorization[len("Bearer "):].strip()
    try:
        payload = decode_token(token, settings.secret_key)
    except pyjwt.PyJWTError as e:
        raise Unauthorized(f"Invalid or expired token: {e}") from e
    user = db.get(User, payload.get("sub", ""))
    if user is None:
        raise Unauthorized("User no longer exists")
    return user
