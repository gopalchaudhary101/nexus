"""Agent tool registry.

Constraints (per spec):
  - tools are the ONLY way an agent touches data; there is no shell, no
    eval, no arbitrary SQL. Each tool is a fixed Python function with a
    declared risk class and explicit parameters.
  - tools that would act on the external world (send_email,
    cancel_subscription) are clearly-marked INTEGRATION STUBS: when approved,
    they return a SIMULATED result with the exact reason (missing
    credentials / provider API) — they never pretend a real action happened.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from ml.anomaly import TransactionAnomalyDetector
from ml.forecasting import forecast_monthly_spending
from ml.risk import assess_message

from ..audit.service import log as audit_log
from ..db.models import Deadline, Document, ModelPrediction, Risk, Subscription, Task, Transaction
from ..llm.factory import get_embedder
from ..rag.retriever import HybridRetriever
from . import policies
from .policies import SAFE, SENSITIVE

UTC = UTC


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(d: object) -> str:
    return d.isoformat() if isinstance(d, datetime) else str(d)


def _txn_rows(db, user_id: str, limit: int = 3000) -> list[Transaction]:
    from sqlalchemy import select
    rows = db.execute(
        select(Transaction).where(Transaction.user_id == user_id)
        .order_by(Transaction.date.desc()).limit(limit)
    ).scalars().all()
    return list(reversed(rows))


# ── tool implementations ─────────────────────────────────────────────────

def t_search_documents(db, user_id: str, query: str, doc_type: str | None = None) -> dict:
    ret = HybridRetriever(get_embedder())
    hits = ret.search(db, user_id, query, top_k=5, doc_type=doc_type)
    return {
        "count": len(hits),
        "hits": [{
            "document": h.document_name, "type": h.doc_type, "page": h.page,
            "score": h.score, "ref": f"{h.document_name} — Page {h.page}",
            "excerpt": h.text[:400],
        } for h in hits],
    }


def t_search_transactions(db, user_id: str, days: int = 365, min_amount: float = 0.0) -> dict:
    from sqlalchemy import select
    cutoff = _now() - timedelta(days=days)
    rows = db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.date >= cutoff,
            Transaction.amount >= min_amount,
        ).order_by(Transaction.date.desc())
    ).scalars().all()
    return {
        "count": len(rows),
        "total_amount": round(sum(r.amount for r in rows), 2),
        "currency": rows[0].currency if rows else "INR",
        "transactions": [{
            "date": r.date.isoformat(), "description": r.description,
            "amount": r.amount, "currency": r.currency,
        } for r in rows[:50]],
    }


def t_list_subscriptions(db, user_id: str) -> dict:
    from sqlalchemy import select
    rows = db.execute(select(Subscription).where(Subscription.user_id == user_id)
                      .order_by(Subscription.annualized_cost.desc())).scalars().all()
    subs = []
    for r in rows:
        try:
            inc = json.loads(r.price_increase_json or "null")
        except ValueError:
            inc = None
        subs.append({
            "id": r.id, "merchant": r.merchant, "amount": r.amount,
            "currency": r.currency,
            "frequency": r.frequency, "status": r.status,
            "next_due": r.next_due.isoformat(),
            "monthly_equivalent": r.monthly_equivalent,
            "annualized_cost": r.annualized_cost,
            "confidence": r.confidence,
            "price_increase": inc,
            "notes": json.loads(r.notes_json or "[]"),
        })
    return {"count": len(subs), "subscriptions": subs,
            "monthly_total": round(sum(s["monthly_equivalent"] for s in subs), 2),
            "annual_total": round(sum(s["annualized_cost"] for s in subs), 2)}


def t_detect_anomalies(db, user_id: str) -> dict:
    txns = _txn_rows(db, user_id)
    if len(txns) < 8:
        return {"ok": False,
                "message": f"Not enough transaction history ({len(txns)} rows; need >= 8) "
                           "to run anomaly detection reliably."}
    rows = [{"date": t.date, "description": t.description, "amount": t.amount,
             "currency": t.currency, "merchant_key": t.description, "id": t.id}
            for t in txns]
    det = TransactionAnomalyDetector().fit(rows)
    results = det.predict(rows)
    flagged = sorted((r for r in results if r.label != "NORMAL"),
                     key=lambda r: r.score, reverse=True)[:10]
    by_idx = {r.index: rows[r.index] for r in flagged}
    out = [{
        "transaction_id": by_idx[f.index]["id"],
        "date": _iso(by_idx[f.index]["date"]),
        "description": by_idx[f.index]["description"],
        "amount": by_idx[f.index]["amount"],
        "label": f.label, "score": f.score, "model": f.model,
        "explanations": f.explanations,
    } for f in flagged]
    db.add(ModelPrediction(
        user_id=user_id, model=det.model_name, task="anomaly",
        payload_json=json.dumps({"n_scored": len(txns), "flagged": out}, default=str),
        metrics_json=json.dumps({"model": det.model_name,
                                 "flagged_count": len(out),
                                 "thresholds": "p95/p99 self-calibrated"}),
    ))
    db.commit()
    return {"ok": True, "model": det.model_name, "n_scored": len(txns),
            "flagged": out,
            "note": "Anomaly != fraud. Unusual transactions — review recommended."}


def _deadline_risk(days: int, amount: float | None, importance: int) -> str:
    if days < 0:
        return "CRITICAL"
    if days <= 3:
        return "CRITICAL" if (importance >= 4 or (amount or 0) >= 5000) else "HIGH"
    if days <= 7:
        return "HIGH" if importance >= 4 else "MEDIUM"
    if days <= 30:
        return "MEDIUM"
    return "LOW"


def t_list_deadlines(db, user_id: str, days: int = 30) -> dict:
    from sqlalchemy import select
    today = date.today()
    horizon = today + timedelta(days=days)
    rows = db.execute(
        select(Deadline).where(
            Deadline.user_id == user_id,
            Deadline.due_date <= horizon,
        ).order_by(Deadline.due_date)
    ).scalars().all()
    out = []
    for r in rows:
        d = (r.due_date - today).days
        out.append({
            "id": r.id, "title": r.title, "kind": r.kind,
            "due_date": r.due_date.isoformat(), "days_remaining": d,
            "risk_level": _deadline_risk(d, r.amount, r.importance),
            "amount": r.amount, "currency": r.currency,
            "source_ref": r.source_ref, "importance": r.importance,
            "notes": r.notes,
        })
    return {"count": len(out), "deadlines": out}


def t_get_forecast(db, user_id: str) -> dict:
    txns = [{"date": t.date, "amount": t.amount, "description": t.description}
            for t in _txn_rows(db, user_id)]
    fc = forecast_monthly_spending(txns, date.today(), horizon=3)
    db.add(ModelPrediction(
        user_id=user_id, model=fc.model, task="forecast",
        payload_json=json.dumps({"ok": fc.ok, "points": fc.points}, default=str),
        metrics_json=json.dumps({"months_of_history": len(fc.history),
                                 "trend_pct_mom": fc.trend_pct_mom}),
    ))
    db.commit()
    return {"ok": fc.ok, "message": fc.message, "model": fc.model,
            "history": fc.history, "points": fc.points, "trend_pct_mom": fc.trend_pct_mom}


def t_analyze_risk(db, user_id: str, text: str) -> dict:
    report = assess_message(text)
    risk = Risk(
        user_id=user_id, kind="SCAM", subject=(text or "")[:120],
        score=report.score, level=report.risk_level,
        signals_json=json.dumps(report.signals, default=str),
        components_json=json.dumps(report.components, default=str),
        disclaimer=report.disclaimer,
    )
    db.add(risk)
    db.commit()
    from .memory import nudge_risk_graph
    nudge_risk_graph(db, user_id, risk)
    if report.risk_level == "HIGH":
        from ..services.notify import notify
        notify(db, user_id, "RISK", "Suspicious message detected",
               f"Risk score {report.score:.2f}. Review the signals before acting.", "WARN")
    return {"risk_level": report.risk_level, "score": report.score,
            "signals": report.signals, "components": report.components,
            "disclaimer": report.disclaimer}


def t_build_insight_report(db, user_id: str, focus: str = "attention") -> dict:
    from sqlalchemy import select
    today = date.today()
    dl = t_list_deadlines(db, user_id, days=14)
    risks = db.execute(
        select(Risk).where(Risk.user_id == user_id, Risk.resolved == False)  # noqa: E712
        .order_by(Risk.created_at.desc()).limit(10)
    ).scalars().all()
    subs = t_list_subscriptions(db, user_id)
    rep = {
        "focus": focus,
        "high_priority_deadlines": [d for d in dl["deadlines"]
                                    if d["risk_level"] in ("HIGH", "CRITICAL")],
        "upcoming_deadlines": [d for d in dl["deadlines"]
                               if d["risk_level"] not in ("HIGH", "CRITICAL")],
        "open_risks": [{
            "kind": r.kind, "subject": r.subject, "level": r.level, "score": r.score,
            "signals": json.loads(r.signals_json or "[]"),
        } for r in risks],
        "subscriptions": subs["subscriptions"],
        "subscription_monthly_total": subs["monthly_total"],
        "subscription_annual_total": subs["annual_total"],
        "generated_on": today.isoformat(),
    }
    return rep


def t_create_reminder(db, user_id: str, title: str, due_date: str) -> dict:
    task = Task(user_id=user_id, title=title[:255], kind="REMINDER",
                due_date=date.fromisoformat(due_date), source="agent")
    db.add(task)
    db.commit()
    audit_log(db, user_id, "reminder.created", actor="agent", target=title)
    return {"created": True, "task_id": task.id, "title": title, "due_date": due_date}


def t_prepare_email(db, user_id: str, to: str, subject: str, body: str) -> dict:
    task = Task(user_id=user_id, title=f"Email draft: {subject[:80]}",
                detail=f"To: {to}\n\n{body}", kind="EMAIL_DRAFT", source="agent")
    db.add(task)
    db.commit()
    audit_log(db, user_id, "email.draft_prepared", actor="agent", target=to)
    return {"draft_id": task.id, "to": to, "subject": subject,
            "note": "Draft saved. Nothing was sent."}


def t_send_email(db, user_id: str, to: str, subject: str, body: str) -> dict:
    # INTEGRATION STUB — clearly marked, never fakes success.
    audit_log(db, user_id, "email.send_attempted", actor="agent", target=to,
              detail={"status": "SIMULATED",
                      "reason": "SMTP integration not configured"})
    return {
        "status": "SIMULATED",
        "to": to, "subject": subject,
        "reason": ("External integration requires credentials (SMTP host/user/password) "
                   "that are not configured in this deployment. No email was sent. "
                   "A draft was prepared instead."),
    }


def t_cancel_subscription(db, user_id: str, merchant: str) -> dict:
    # INTEGRATION STUB — bank/UPI/provider API not available offline.
    from sqlalchemy import select
    sub = db.execute(select(Subscription).where(
        Subscription.user_id == user_id, Subscription.merchant == merchant
    )).scalar_one_or_none()
    audit_log(db, user_id, "subscription.cancel_attempted", actor="agent",
              target=merchant, detail={"status": "SIMULATED"})
    if sub is None:
        return {"status": "NOT_FOUND", "merchant": merchant}
    return {
        "status": "SIMULATED",
        "merchant": merchant,
        "reason": ("Provider cancellation requires a bank/UPI API integration which is "
                   "not configured. Nothing was cancelled. Please cancel via the "
                   "provider's app or bank directly."),
    }


def t_delete_document(db, user_id: str, doc_id: str) -> dict:
    from pathlib import Path

    from sqlalchemy import delete as sa_delete

    from ..db.models import DocumentChunk, DocumentEntity
    from ..services.graph import delete_document_graph
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user_id:
        return {"deleted": False, "reason": "Document not found (or not yours)."}
    db.execute(sa_delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
    db.execute(sa_delete(DocumentEntity).where(DocumentEntity.document_id == doc_id))
    delete_document_graph(db, user_id, doc_id)
    if Path(doc.stored_path).exists():
        Path(doc.stored_path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    audit_log(db, user_id, "document.deleted", actor="agent", target=doc.filename)
    return {"deleted": True, "filename": doc.filename}


def t_get_document(db, user_id: str, doc_id: str) -> dict:
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user_id:
        return {"found": False}
    return {"found": True, "filename": doc.filename, "type": doc.doc_type,
            "status": doc.status, "text_preview": doc.text[:1500]}


# ── registry ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk_class: str
    params: tuple[str, ...]
    fn: Callable


TOOLS: dict[str, ToolSpec] = {
    s.name: s
    for s in [
        ToolSpec("search_documents", "Semantic + keyword search across the user's documents.",
                 SAFE, ("query", "doc_type"), t_search_documents),
        ToolSpec("get_document", "Fetch one document's metadata and preview.",
                 SAFE, ("doc_id",), t_get_document),
        ToolSpec("search_transactions", "Query transaction history by time/amount.",
                 SAFE, ("days", "min_amount"), t_search_transactions),
        ToolSpec("list_subscriptions", "List detected subscriptions with costs.",
                 SAFE, (), t_list_subscriptions),
        ToolSpec("detect_anomalies", "Run the anomaly detector on transactions.",
                 SAFE, (), t_detect_anomalies),
        ToolSpec("list_deadlines", "List deadlines within N days with risk levels.",
                 SAFE, ("days",), t_list_deadlines),
        ToolSpec("get_forecast", "Monthly spending forecast (or explicit insufficient-data).",
                 SAFE, (), t_get_forecast),
        ToolSpec("analyze_risk", "Multi-signal scam/risk assessment of a message.",
                 SAFE, ("text",), t_analyze_risk),
        ToolSpec("build_insight_report", "Aggregate a prioritized insight report.",
                 SAFE, ("focus",), t_build_insight_report),
        ToolSpec("create_reminder", "Create a reminder task.",
                 SENSITIVE, ("title", "due_date"), t_create_reminder),
        ToolSpec("prepare_email", "Prepare (but do not send) an email draft.",
                 SENSITIVE, ("to", "subject", "body"), t_prepare_email),
        ToolSpec("send_email", "Send an email (INTEGRATION STUB — simulated without SMTP).",
                 policies.TOOL_POLICY["send_email"], ("to", "subject", "body"), t_send_email),
        ToolSpec("cancel_subscription", "Cancel a subscription (INTEGRATION STUB).",
                 policies.TOOL_POLICY["cancel_subscription"], ("merchant",), t_cancel_subscription),
        ToolSpec("delete_document", "Delete a document and its derived data.",
                 policies.TOOL_POLICY["delete_document"], ("doc_id",), t_delete_document),
    ]
}
