from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "service": "nexus-api",
        "version": "0.1.0",
        "llm_provider": "mock" if s.llm_provider == "mock" else "configured",
        "embed_provider": s.embed_provider,
        "db": "postgres" if s.using_postgres else "sqlite",
        "pgvector": bool(s.using_postgres and s.use_pgvector),
    }


@router.get("/ready", dependencies=[Depends(get_db)])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ready": True}
    except Exception:
        return {"ready": False}
