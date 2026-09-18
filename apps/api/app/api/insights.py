from __future__ import annotations

import json
from datetime import UTC, date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agents.tools import _deadline_risk
from ..db.models import Approval, Deadline, Document, ModelPrediction, Risk, Subscription, Transaction
from ..db.session import get_db
from ..schemas import AnomalyOut, DeadlineOut, ForecastOut, OverviewOut, SubscriptionOut
from ..services.graph import get_graph
from .deps import get_current_user

router = APIRouter(prefix="/insights", tags=["insights"])

CATEGORIES = ["BILL", "BANK_STATEMENT", "INVOICE", "RECEIPT", "INSURANCE",
              "CONTRACT", "WARRANTY", "SUBSCRIPTION", "TRAVEL", "EDUCATION",
              "EMPLOYMENT", "IDENTITY", "OTHER"]


@router.get("/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    today = date.today()
    docs = db.execute(select(Document).where(Document.user_id == user.id)).scalars().all()
    ready = sum(1 for d in docs if d.status == "READY")
    pending = sum(1 for d in docs if d.status in ("UPLOADED", "PROCESSING", "INDEXING"))

    subs = db.execute(select(Subscription).where(Subscription.user_id == user.id)).scalars().all()
    recurring = round(sum(s.monthly_equivalent for s in subs), 2)
    cur = subs[0].currency if subs else "INR"

    deadlines = db.execute(select(Deadline).where(
        Deadline.user_id == user.id,
        Deadline.due_date >= today,
        Deadline.due_date <= date.fromordinal(today.toordinal() + 30),
    )).scalars().all()
    upcoming = len(deadlines)

    risks = db.execute(select(Risk).where(
        Risk.user_id == user.id, Risk.resolved == False,  # noqa: E712
        Risk.level.in_(["MEDIUM", "HIGH", "CRITICAL"]),
    )).scalars().all()

    pending_approvals = db.execute(select(func.count(Approval.id)).where(
        Approval.user_id == user.id, Approval.status == "PENDING")).scalar_one()

    # needs attention: critical/high deadlines in 14d + open high risks + approvals
    dl14 = [d for d in deadlines
            if (d.due_date - today).days <= 14
            and _deadline_risk((d.due_date - today).days, d.amount, d.importance)
            in ("HIGH", "CRITICAL")]
    hi_risks = [r for r in risks if r.level in ("HIGH", "CRITICAL")]
    needs_attention = len(dl14) + len(hi_risks) + int(pending_approvals)

    # priority feed
    feed: list[dict] = []
    for d in sorted(dl14, key=lambda x: x.due_date):
        days = (d.due_date - today).days
        feed.append({
            "severity": "HIGH" if days <= 7 else "MEDIUM",
            "kind": "DEADLINE", "title": d.title,
            "detail": f"Due {d.due_date.isoformat()} ({days} day(s))"
                      + (f" — {d.currency} {d.amount:,.0f}" if d.amount else ""),
            "ref": d.id,
        })
    for r in hi_risks[:5]:
        feed.append({"severity": "RISK", "kind": "RISK", "title": r.subject[:80],
                     "detail": f"{r.level} risk signal (score {r.score:.2f})", "ref": r.id})
    sub_due = [s for s in subs if (s.next_due - today).days <= 7]
    for s in sub_due[:3]:
        feed.append({"severity": "MEDIUM", "kind": "SUBSCRIPTION",
                     "title": f"{s.merchant} renewal",
                     "detail": f"Next charge {s.next_due.isoformat()} — "
                               f"{s.currency} {s.amount:,.0f} {s.frequency.lower()}",
                     "ref": s.id})

    types_present = {d.doc_type for d in docs}
    coverage = round(len(types_present & set(CATEGORIES)) / len(CATEGORIES), 3)

    return OverviewOut(
        needs_attention=needs_attention, upcoming=upcoming, risk_signals=len(risks),
        recurring_monthly=recurring, recurring_currency=cur, documents=len(docs),
        ready_documents=ready, pending_documents=pending, knowledge_coverage=coverage,
        pending_approvals=int(pending_approvals), recent=feed[:12],
    )


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def subscriptions(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(Subscription).where(Subscription.user_id == user.id)
                      .order_by(Subscription.annualized_cost.desc())).scalars().all()
    out = []
    for r in rows:
        try:
            inc = json.loads(r.price_increase_json or "null")
        except ValueError:
            inc = None
        out.append(SubscriptionOut(
            id=r.id, merchant=r.merchant, raw_merchant=r.raw_merchant,
            amount=r.amount, currency=r.currency, frequency=r.frequency,
            occurrences=r.occurrences, last_date=r.last_date, next_due=r.next_due,
            monthly_equivalent=r.monthly_equivalent, annualized_cost=r.annualized_cost,
            status=r.status, confidence=r.confidence, price_increase=inc,
            notes=json.loads(r.notes_json or "[]"),
        ))
    return out


@router.get("/graph")
def graph(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Personal Knowledge Graph nodes + edges (relational storage)."""
    return get_graph(db, user.id)


@router.get("/anomalies", response_model=list[AnomalyOut])
def anomalies(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from datetime import datetime

    pred = db.execute(select(ModelPrediction).where(
        ModelPrediction.user_id == user.id, ModelPrediction.task == "anomaly"
    ).order_by(ModelPrediction.created_at.desc()).limit(1)).scalar_one_or_none()
    if pred is None:
        return []
    payload = json.loads(pred.payload_json or "{}")
    flagged = payload.get("flagged", [])
    out = []
    for f in flagged:
        # Defense in depth: this payload is generated exclusively by the
        # user's own anomaly-detection job today, so transaction_id can't
        # reference another tenant's row in practice — but scope the lookup
        # by user_id anyway rather than trusting the stored id alone.
        txn = None
        if f.get("transaction_id"):
            txn = db.execute(select(Transaction).where(
                Transaction.id == f["transaction_id"], Transaction.user_id == user.id
            )).scalars().first()
        out.append(AnomalyOut(
            transaction_id=f.get("transaction_id", ""),
            date=txn.date if txn else datetime(2000, 1, 1, tzinfo=UTC),
            description=f.get("description", ""), amount=f.get("amount", 0.0),
            currency=txn.currency if txn else "INR",
            label=f.get("label", "UNUSUAL"), score=f.get("score", 0.0),
            model=f.get("model", ""), explanations=f.get("explanations", []),
        ))
    return out


@router.get("/deadlines", response_model=list[DeadlineOut])
def deadlines(db: Session = Depends(get_db), user=Depends(get_current_user)):
    today = date.today()
    rows = db.execute(select(Deadline).where(Deadline.user_id == user.id)
                      .order_by(Deadline.due_date)).scalars().all()
    out = []
    for r in rows:
        days = (r.due_date - today).days
        out.append(DeadlineOut(
            id=r.id, title=r.title, kind=r.kind, due_date=r.due_date,
            days_remaining=days, risk_level=_deadline_risk(days, r.amount, r.importance),
            source="document", source_ref=r.source_ref, amount=r.amount,
            currency=r.currency, importance=r.importance, notes=r.notes,
        ))
    return out


@router.get("/forecast", response_model=ForecastOut)
def forecast(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from ml.forecasting import forecast_monthly_spending
    rows = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalars().all()
    txns = [{"date": t.date, "amount": t.amount, "description": t.description} for t in rows]
    fc = forecast_monthly_spending(txns, date.today(), horizon=3)
    return ForecastOut(ok=fc.ok, message=fc.message, model=fc.model,
                       history=fc.history, points=fc.points,
                       trend_pct_mom=fc.trend_pct_mom)
