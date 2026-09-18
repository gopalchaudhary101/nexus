"""Create the demo user, ingest the synthetic demo dataset, and run the
detection + evaluation pipelines once. Idempotent (skips if user exists).

Usage:  python3 scripts/seed_demo.py
Login:  demo@nexus.dev / NEXUS_DEMO_PASSWORD (default: nexus-demo-2026)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.config import ROOT as APP_ROOT  # noqa: E402
from app.core.security import (
    hash_password,  # noqa: E402
    safe_filename,  # noqa: E402
)
from app.db.models import (  # noqa: E402
    Document,  # noqa: E402
    User,
)
from app.db.session import create_all, get_session_factory  # noqa: E402
from app.services.evaluation_service import run_rag_evaluation  # noqa: E402
from app.services.ingest import run_ingestion  # noqa: E402
from app.services.storage import store_upload, validate_upload  # noqa: E402

DEMO_EMAIL = "demo@nexus.dev"
DEMO_PASSWORD = os.environ.get("NEXUS_DEMO_PASSWORD", "nexus-demo-2026")


def main() -> None:
    create_all()
    SessionLocal = get_session_factory()
    db = SessionLocal()

    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user is not None:
        print(f"Demo user already exists ({DEMO_EMAIL}); skipping creation.")
    else:
        user = User(email=DEMO_EMAIL, name="Demo User",
                    password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created demo user {DEMO_EMAIL}")

    demo = APP_ROOT / "data" / "demo"
    if not demo.exists():
        print("Demo data missing — run: python3 scripts/generate_demo_data.py")
        return

    files = sorted(list((demo / "documents").glob("*")) + list((demo / "messages").glob("*"))
                   + [demo / "transactions.csv"])
    for path in files:
        existing = db.query(Document).filter(
            Document.user_id == user.id, Document.filename == safe_filename(path.name)
        ).first()
        if existing is not None:
            print(f"  skip {path.name} (already ingested)")
            continue
        data = path.read_bytes()
        ftype = validate_upload(path.name, data)
        doc = Document(user_id=user.id, filename=safe_filename(path.name),
                       stored_path="", file_type=ftype, size_bytes=len(data),
                       mime="")
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc.stored_path = store_upload(user.id, doc.id, path.name, data)
        db.commit()
        run_ingestion(doc.id)
        db.refresh(doc)
        print(f"  {path.name:38s} -> {doc.status} {doc.status_detail[:70]}")

    # recurring subscriptions from transaction history (shared service)
    from app.services.transactions import refresh_subscriptions_for_user
    subs = refresh_subscriptions_for_user(db, user.id)
    print(f"Subscriptions detected: {len(subs)}")
    for s in subs:
        print(f"  {s.merchant:28s} {s.frequency:10s} {s.amount:>8.0f} "
              f"~{s.annualized_cost:>9.0f}/yr {s.status}"
              + (f" price +{s.price_increase['pct']}%" if s.price_increase else ""))

    # risk analysis of the bundled suspicious message
    import json as _json

    from app.agents.memory import nudge_risk_graph
    from app.db.models import Risk

    from ml.risk import assess_message
    msg = (demo / "messages" / "suspicious_message.txt").read_text()
    report = assess_message(msg)
    risk = Risk(user_id=user.id, kind="SCAM", subject=msg[:120], score=report.score,
                level=report.risk_level, signals_json=_json.dumps(report.signals),
                components_json=_json.dumps(report.components),
                disclaimer=report.disclaimer)
    db.add(risk)
    db.commit()
    nudge_risk_graph(db, user.id, risk)
    print(f"Suspicious message risk: {report.risk_level} (score {report.score})")

    # anomaly detection (stores ModelPrediction for the DataLab page)
    from app.agents.tools import t_detect_anomalies
    anom = t_detect_anomalies(db, user.id)
    print(f"Anomalies: {anom.get('flagged', 'insufficient data') if isinstance(anom.get('flagged'), list) else anom}")
    flagged = anom.get("flagged", [])
    for f in flagged[:5]:
        print(f"  {f['label']:16s} {f['score']:.3f}  {f['description'][:40]}  {f['date'][:10]}  {f['amount']}")

    # one agent run so the Agent Trace page has real steps
    from app.agents.executor import run_agent
    run = run_agent(db, user.id, "What needs my attention this week?")
    print(f"Agent run: {run.id} status={run.status} intent={run.intent}")

    # RAG evaluation (real metrics from the live pipeline)
    report = run_rag_evaluation(db, user.id)
    if "metrics" in report:
        m = report["metrics"]
        print(f"RAG eval: P@1={m['precision_at_1']} R@5={m['recall_at_5']} "
              f"citations={m['citation_accuracy']} answer_ok={m['answer_correctness']} "
              f"latency={m['latency_ms_avg']}ms (n={report['n_cases']})")
    else:
        print(f"RAG eval: {report}")

    print("\nSeed complete. Login with:")
    print(f"  email:    {DEMO_EMAIL}")
    print(f"  password: {DEMO_PASSWORD}")
    db.close()


if __name__ == "__main__":
    main()
