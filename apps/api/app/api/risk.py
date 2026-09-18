from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ml.risk import assess_message

from ..agents.memory import nudge_risk_graph
from ..audit.service import log as audit_log
from ..core.errors import ApiError, NotFound
from ..db.models import Document, Risk
from ..db.session import get_db
from ..schemas import RiskAnalyzeIn, RiskOut
from ..services.notify import notify
from .deps import get_current_user

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/analyze", response_model=RiskOut)
def analyze(body: RiskAnalyzeIn, db: Session = Depends(get_db),
            user=Depends(get_current_user)):
    text = body.text
    if text is None and body.document_id:
        doc = db.get(Document, body.document_id)
        if doc is None or doc.user_id != user.id:
            raise NotFound("Document not found")
        text = doc.text[:8000]
    if not text or not text.strip():
        raise ApiError("Provide 'text' or a 'document_id' to analyze", code="empty_input")
    report = assess_message(text, sender=body.sender, claimed_brand=body.claimed_brand)
    risk = Risk(
        user_id=user.id, kind="SCAM", subject=text[:120],
        score=report.score, level=report.risk_level,
        signals_json=json.dumps(report.signals, default=str),
        components_json=json.dumps(report.components, default=str),
        disclaimer=report.disclaimer,
    )
    db.add(risk)
    db.commit()
    nudge_risk_graph(db, user.id, risk)
    audit_log(db, user.id, "risk.analyzed", actor="user", target=text[:60],
              detail={"level": report.risk_level, "score": report.score})
    if report.risk_level == "HIGH":
        notify(db, user.id, "RISK", "Suspicious message detected",
               f"Risk score {report.score:.2f} — review the signals before acting.", "WARN")
    return RiskOut(id=risk.id, risk_level=report.risk_level, score=report.score,
                   signals=report.signals, components=report.components,
                   disclaimer=report.disclaimer, subject=risk.subject)
