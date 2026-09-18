from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import NotFound
from ..db.models import Notification
from ..db.session import get_db
from ..schemas import NotificationOut
from .deps import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(limit: int = 50, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    rows = db.execute(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.created_at.desc()).limit(limit)
                      ).scalars().all()
    return [NotificationOut.model_validate(r) for r in rows]


@router.post("/{notif_id}/read", status_code=204)
def mark_read(notif_id: str, db: Session = Depends(get_db),
              user=Depends(get_current_user)):
    n = db.get(Notification, notif_id)
    if n is None or n.user_id != user.id:
        raise NotFound("Notification not found")
    n.read = True
    db.commit()
    return None


@router.post("/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(Notification).where(
        Notification.user_id == user.id, Notification.read == False)).scalars().all()  # noqa: E712
    for n in rows:
        n.read = True
    db.commit()
    return None
