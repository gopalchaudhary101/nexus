"""End-to-end scenario (spec §43/§59): register -> upload demo data ->
process -> index -> ask -> retrieve source -> analyze -> evaluate.

Uses the committed synthetic demo dataset. This is the acceptance test for
the core product loop.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.main import create_app  # noqa: E402  (env set by apps/api/tests/conftest? no—standalone below)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    tmp = tmp_path_factory.mktemp("e2e")
    os.environ["NEXUS_DATABASE_URL"] = f"sqlite:///{tmp}/e2e.db"
    os.environ["NEXUS_UPLOAD_DIR"] = str(tmp / "uploads")
    os.environ["NEXUS_SECRET_KEY"] = "e2e-secret"
    os.environ["NEXUS_LLM_PROVIDER"] = "mock"
    # force a fresh engine for this module
    import app.db.session as sess
    if sess._engine is not None:
        sess._engine.dispose()
        sess._engine = None
        sess._SessionLocal = None
    from fastapi.testclient import TestClient
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def demo(client):
    email = "e2e@example.com"
    r = client.post("/api/v1/auth/register",
                    json={"email": email, "password": "e2e-secret-99", "name": "E2E"})
    assert r.status_code == 200
    tok = r.json()["access_token"]
    return {"token": tok}


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def _wait(client, tok, doc_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = client.get(f"/api/v1/documents/{doc_id}", headers=_auth(tok)).json()
        if d["status"] in ("READY", "FAILED"):
            return d
        time.sleep(0.3)
    raise TimeoutError(doc_id)


def test_full_loop(client, demo):
    tok = demo["token"]
    demo_dir = ROOT / "data" / "demo"
    assert demo_dir.exists(), "run scripts/generate_demo_data.py first"

    uploaded = []
    for f in sorted((demo_dir / "documents").iterdir()) + [demo_dir / "transactions.csv"]:
        r = client.post("/api/v1/documents/upload",
                        files={"file": (f.name, f.read_bytes(), "application/octet-stream")},
                        headers=_auth(tok))
        assert r.status_code == 202, r.text
        uploaded.append(r.json()["id"])
    for doc_id in uploaded:
        d = _wait(client, tok, doc_id)
        assert d["status"] == "READY", f"{d['filename']}: {d['status_detail']}"

    # grounded, source-cited answer
    r = client.post("/api/v1/ask",
                    json={"question": "When does my insurance policy expire?"},
                    headers=_auth(tok))
    body = r.json()
    assert body["grounded"] is True
    assert "14 March 2027" in body["answer"]
    assert body["sources"][0]["document_name"] == "insurance_policy.pdf"

    # subscription intelligence from transactions
    r = client.get("/api/v1/insights/subscriptions", headers=_auth(tok))
    subs = {s["merchant"]: s for s in r.json()}
    assert "Example Streaming" in subs
    assert subs["Example Streaming"]["annualized_cost"] > 9000
    cloud = next((s for k, s in subs.items() if "cloudvault" in k.lower()), None)
    assert cloud is not None, list(subs)
    assert cloud["price_increase"] is not None

    # risk engine on the bundled suspicious message
    msg = (demo_dir / "messages" / "suspicious_message.txt").read_text()
    r = client.post("/api/v1/risk/analyze", json={"text": msg}, headers=_auth(tok))
    assert r.json()["risk_level"] == "HIGH"

    # agent: weekly attention (HITL gate included)
    r = client.post("/api/v1/agent/run",
                    json={"request": "What needs my attention this week?"},
                    headers=_auth(tok))
    last = {}
    for line in r.text.splitlines():
        if line.startswith("data: "):
            last = json.loads(line[6:])
    assert last["type"] == "done"
    assert last["status"] == "WAITING_APPROVAL"  # reminder step gated

    # RAG evaluation on the live pipeline — real metrics
    r = client.post("/api/v1/analytics/rag-quality/run", headers=_auth(tok))
    assert r.status_code == 200
    rep = r.json()
    assert rep["evaluated"] is True
    assert rep["n_cases"] == 12
    assert rep["metrics"]["retrieval_precision_at_1"] >= 0.9
    assert rep["metrics"]["retrieval_recall_at_5"] == 1.0
    assert rep["metrics"]["citation_accuracy"] >= 0.9
    assert rep["metrics"]["answer_correctness"] >= 0.9

    # knowledge graph has real nodes/edges
    r = client.get("/api/v1/insights/graph", headers=_auth(tok))
    g = r.json()
    kinds = {n["kind"] for n in g["nodes"]}
    assert "DOCUMENT" in kinds and "DEADLINE" in kinds
    assert len(g["edges"]) > 10

    # analytics overview
    r = client.get("/api/v1/analytics/overview", headers=_auth(tok))
    ov = r.json()
    assert ov["transactions"] >= 100
    assert ov["documents"] >= 10
    assert ov["audit_events"] > 0
