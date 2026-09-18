from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.executor import resume_after_approval
from ..audit.service import log as audit_log
from ..core.errors import ApiError, NotFound
from ..db.models import Approval
from ..db.session import get_db
from ..schemas import ApprovalOut
from .deps import get_current_user

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _get_approval_or_404(db: Session, user_id: str, approval_id: str) -> Approval:
    a = db.get(Approval, approval_id)
    if a is None or a.user_id != user_id:
        raise NotFound("Approval not found")
    if a.status != "PENDING":
        raise ApiError(f"Approval already {a.status.lower()}", code="already_decided")
    return a


@router.get("", response_model=list[ApprovalOut])
def list_approvals(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(Approval).where(Approval.user_id == user.id)
                      .order_by(Approval.created_at.desc()).limit(100)).scalars().all()
    return [ApprovalOut(
        id=a.id, run_id=a.run_id, tool=a.tool, risk_class=a.risk_class,
        args=__import__("json").loads(a.args_json or "{}"), status=a.status,
        result=__import__("json").loads(a.result_json) if a.result_json else None,
        created_at=a.created_at, decided_at=a.decided_at) for a in rows]


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
def approve(approval_id: str, db: Session = Depends(get_db),
            user=Depends(get_current_user)):
    a = _get_approval_or_404(db, user.id, approval_id)
    run = resume_after_approval(db, a, approved=True)
    audit_log(db, user.id, "approval.approved", actor="user", target=a.tool,
              detail={"approval_id": a.id, "run_id": a.run_id,
                      "run_status": run.status if run else None})
    db.refresh(a)
    return ApprovalOut(
        id=a.id, run_id=a.run_id, tool=a.tool, risk_class=a.risk_class,
        args=__import__("json").loads(a.args_json or "{}"), status=a.status,
        result=__import__("json").loads(a.result_json) if a.result_json else None,
        created_at=a.created_at, decided_at=a.decided_at)


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
def reject(approval_id: str, db: Session = Depends(get_db),
            user=Depends(get_current_user)):
    a = _get_approval_or_404(db, user.id, approval_id)
    run = resume_after_approval(db, a, approved=False)
    audit_log(db, user.id, "approval.rejected", actor="user", target=a.tool,
              detail={"approval_id": a.id, "run_status": run.status if run else None})
    db.refresh(a)
    return ApprovalOut(
        id=a.id, run_id=a.run_id, tool=a.tool, risk_class=a.risk_class,
        args=__import__("json").loads(a.args_json or "{}"), status=a.status,
        result=None, created_at=a.created_at, decided_at=a.decided_at)
