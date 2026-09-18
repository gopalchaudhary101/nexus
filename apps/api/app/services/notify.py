"""In-app notifications (email/push are optional integrations)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import Notification


def notify(db: Session, user_id: str, kind: str, title: str,
           body: str = "", severity: str = "INFO") -> None:
    db.add(Notification(user_id=user_id, kind=kind, title=title[:255],
                        body=body, severity=severity))
    db.commit()
