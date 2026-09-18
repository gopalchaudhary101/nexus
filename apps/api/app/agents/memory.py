"""Safe, user-scoped agent memory.

Separation (per spec):
  - conversation: rolling window of recent agent requests (scope=conversation)
  - preference:   explicit user preferences (scope=preference)
  - state:        scratch task state (scope=state)
Nothing is stored blindly; every entry is key/value, user-scoped, and
deletable (wipe_user_memory is called on account deletion).
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import KnowledgeEntity, MemoryEntry


def _get(db: Session, user_id: str, scope: str, key: str) -> Any:
    row = db.execute(select(MemoryEntry).where(
        MemoryEntry.user_id == user_id,
        MemoryEntry.scope == scope,
        MemoryEntry.key == key,
    )).scalar_one_or_none()
    if row is None:
        return None
    return json.loads(row.value_json or "null")


def _set(db: Session, user_id: str, scope: str, key: str, value: Any) -> None:
    row = db.execute(select(MemoryEntry).where(
        MemoryEntry.user_id == user_id,
        MemoryEntry.scope == scope,
        MemoryEntry.key == key,
    )).scalar_one_or_none()
    payload = json.dumps(value, default=str)
    if row is None:
        db.add(MemoryEntry(user_id=user_id, scope=scope, key=key, value_json=payload))
    else:
        row.value_json = payload
    db.commit()


def record_request(db: Session, user_id: str, request: str) -> None:
    hist = _get(db, user_id, "conversation", "last_requests") or []
    hist = [r for r in hist if r != request][-9:]
    hist.append(request[:400])
    _set(db, user_id, "conversation", "last_requests", hist)


def recent_requests(db: Session, user_id: str, n: int = 5) -> list[str]:
    hist = _get(db, user_id, "conversation", "last_requests") or []
    return hist[-n:]


def set_preference(db: Session, user_id: str, key: str, value: Any) -> None:
    prefs = _get(db, user_id, "preference", "all") or {}
    prefs[key] = value
    _set(db, user_id, "preference", "all", prefs)


def get_preferences(db: Session, user_id: str) -> dict:
    return _get(db, user_id, "preference", "all") or {}


def nudge_risk_graph(db: Session, user_id: str, risk) -> None:
    from ..services.graph import _user_name, add_rel, upsert_entity

    user_node = upsert_entity(db, user_id, "USER", _user_name(db, user_id))
    node = upsert_entity(db, user_id, "RISK",
                         f"{risk.kind} risk ({risk.level})",
                         {"score": risk.score, "subject": risk.subject[:120]},
                         ref_id=risk.id)
    add_rel(db, user_id, user_node, "RELATED_TO", node)


def wipe_user_memory(db: Session, user_id: str) -> int:
    from ..db.models import KnowledgeRelationship

    rows = db.execute(select(MemoryEntry).where(MemoryEntry.user_id == user_id)).scalars().all()
    for r in rows:
        db.delete(r)
    db.execute(delete(KnowledgeEntity).where(KnowledgeEntity.user_id == user_id))
    db.execute(delete(KnowledgeRelationship).where(KnowledgeRelationship.user_id == user_id))
    db.commit()
    return len(rows)
