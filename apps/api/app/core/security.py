"""Auth primitives: password hashing (PBKDF2-SHA256) and HS256 JWT.

Password hashing uses the standard library (200k iterations PBKDF2).
For production deployments with >1000 users, argon2id is recommended;
the interface (hash_password/verify_password) is deliberately isolated so
the swap is a one-file change.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta

import jwt

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, dk_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def create_token(subject: str, secret: str, ttl_hours: int = 8) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    return jwt.decode(token, secret, algorithms=["HS256"])


class RateLimiter:
    """Fixed-window in-memory limiter (per key). Process-local; in a
    multi-instance deployment move to Redis — interface unchanged."""

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            window = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(window) >= self.max_requests:
                self._hits[key] = window
                return False
            window.append(now)
            self._hits[key] = window
            return True


_limiter_instance: RateLimiter | None = None


def auth_limiter_factory() -> RateLimiter:
    """Process-wide limiter for auth endpoints (fixed window)."""
    global _limiter_instance
    if _limiter_instance is None:
        from .config import get_settings
        _limiter_instance = RateLimiter(max_requests=get_settings().auth_rate_limit)
    return _limiter_instance


def safe_filename(name: str, max_len: int = 80) -> str:
    base = os.path.basename(name or "file")
    return "".join(c for c in base if c.isalnum() or c in "._-")[:max_len] or "file"
