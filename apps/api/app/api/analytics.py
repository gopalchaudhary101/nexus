from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit.service import log as audit_log
from ..db.models import (
    AgentRun,
    AuditEvent,
    Deadline,
    Document,
    DocumentChunk,
    RagEvalResult,
    Risk,
    Subscription,
    Transaction,
)
from ..db.session import get_db
from ..schemas import OverviewAnalyticsOut, RagQualityOut, RiskAnalyticsOut, SpendingOut
from .deps import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewAnalyticsOut)
def overview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    def count(model):
        return db.execute(select(func.count(model.id)).where(
            model.user_id == user.id)).scalar_one()
    storage = db.execute(select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
        Document.user_id == user.id)).scalar_one()
    return OverviewAnalyticsOut(
        documents=count(Document), chunks=count(DocumentChunk),
        transactions=count(Transaction), subscriptions=count(Subscription),
        deadlines=count(Deadline), risks=count(Risk), agent_runs=count(AgentRun),
        audit_events=count(AuditEvent), storage_bytes=int(storage or 0),
    )


@router.get("/spending", response_model=SpendingOut)
def spending(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from ml.forecasting.model import monthly_totals
    rows = db.execute(select(Transaction).where(
        Transaction.user_id == user.id)).scalars().all()
    txns = [{"date": t.date, "amount": t.amount, "description": t.description} for t in rows]
    hist = monthly_totals(txns, date.today(), months=12)
    subs = db.execute(select(Subscription).where(
        Subscription.user_id == user.id)).scalars().all()
    recurring = round(sum(s.monthly_equivalent for s in subs), 2)
    cur = subs[0].currency if subs else "INR"
    months = []
    for h in hist:
        months.append({
            "month": h["month"], "total": h["total"],
            "recurring": min(recurring, h["total"]) if h["total"] > 0 else 0,
            "other": max(0.0, round(h["total"] - min(recurring, h["total"]), 2)),
        })
    return SpendingOut(currency=cur, months=months)


def _latest_eval(db: Session) -> RagQualityOut:
    latest = db.execute(select(RagEvalResult).order_by(
        RagEvalResult.created_at.desc()).limit(1)).scalar_one_or_none()
    if latest is None:
        return RagQualityOut(evaluated=False,
                             message=("Not yet evaluated. Trigger an evaluation "
                                      "run against your ingested documents "
                                      "(POST /analytics/rag-quality/run)."))
    run_id = latest.run_id
    rows = db.execute(select(RagEvalResult).where(RagEvalResult.run_id == run_id)
                      ).scalars().all()
    n = len(rows)
    metrics = {
        "retrieval_precision_at_1": round(sum(r.precision_at_1 for r in rows) / n, 3),
        "retrieval_recall_at_5": round(sum(r.recall_at_5 for r in rows) / n, 3),
        "citation_accuracy": round(sum(r.citation_accuracy for r in rows) / n, 3),
        "answer_correctness": round(sum(r.answer_correctness for r in rows) / n, 3),
        "latency_ms_avg": round(sum(r.latency_ms for r in rows) / n, 1),
    }
    detail = [{
        "id": r.id, "question": r.question, "expected_doc": r.expected_doc,
        "top1_doc": r.top1_doc, "answer": r.answer[:300],
        "precision_at_1": r.precision_at_1, "recall_at_5": r.recall_at_5,
        "citation_accuracy": r.citation_accuracy,
        "answer_correctness": r.answer_correctness, "latency_ms": r.latency_ms,
    } for r in rows]
    return RagQualityOut(
        evaluated=True, generated_at=latest.created_at.isoformat(), n_cases=n,
        metrics=metrics, rows=detail,
    )


@router.get("/rag-quality", response_model=RagQualityOut)
def rag_quality(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _latest_eval(db)


@router.post("/rag-quality/run", response_model=RagQualityOut)
def run_eval(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Run the internal evaluation dataset against the live RAG pipeline and
    persist real per-case results. Metrics are computed, never hardcoded."""
    from ..services.evaluation_service import run_rag_evaluation

    report = run_rag_evaluation(db, user.id)
    if "error" in report:
        return RagQualityOut(evaluated=False, message=report["error"])
    audit_log(db, user.id, "rag.evaluated", actor="user",
              target=report.get("generated_at", ""),
              detail={"metrics": report.get("metrics", {})})
    return _latest_eval(db)


@router.get("/risk", response_model=RiskAnalyticsOut)
def risk(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(Risk).where(Risk.user_id == user.id)
                      .order_by(Risk.created_at.desc())).scalars().all()
    by_level: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    for r in rows:
        by_level[r.level] = by_level.get(r.level, 0) + 1
        try:
            signals = json.loads(r.signals_json or "[]")
        except ValueError:
            signals = []
        for s in signals:
            label = s.get("label", s.get("id", "unknown"))
            signal_counts[label] = signal_counts.get(label, 0) + 1
    top = sorted(signal_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
    return RiskAnalyticsOut(
        total=len(rows), by_level=by_level,
        top_signals=[{"label": k, "count": v} for k, v in top],
        recent=[{"id": r.id, "subject": r.subject, "level": r.level,
                 "score": r.score, "created_at": r.created_at.isoformat()}
                for r in rows[:10]],
    )
