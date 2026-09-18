"""Append-only audit trail. Every consequential event (auth, upload,
delete, approval decision, agent tool execution, data wipe) is logged with
actor + target + detail. Events are never updated or deleted by the app."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..db.models import AuditEvent


def log(db: Session, user_id: str | None, action: str, actor: str = "user",
        target: str = "", detail: dict | None = None) -> None:
    db.add(AuditEvent(
        user_id=user_id, actor=actor, action=action, target=target[:255],
        detail_json=json.dumps(detail or {}, default=str),
    ))
    db.commit()
