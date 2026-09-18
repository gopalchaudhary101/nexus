"""Engine/session management. Local default is SQLite; Postgres(+pgvector)
is the deployment target (see docker-compose.yml)."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_settings
from .base import Base

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        return
    settings = get_settings()
    url = settings.db_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        from pathlib import Path
        db_path = Path(url.replace("sqlite:///", "", 1))
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(url, **kwargs)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def get_engine():
    if _engine is None:
        init_db()
    return _engine


def get_session_factory():
    factory = _SessionLocal
    if factory is None:
        init_db()
        factory = _SessionLocal
    assert factory is not None
    return factory


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    init_db()
    Base.metadata.create_all(get_engine())
