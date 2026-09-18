"""Agent framework tests: runs, traces, policy gate, approvals, audit."""
from __future__ import annotations

import json

from .conftest import auth, sse_final, upload, wait_ready

DATA_CSV = """date,description,amount,currency,category
2026-07-02 09:00,ACME STREAMING SUBSCRIPTION,599,INR,Subscriptions
2026-08-02 09:00,ACME STREAMING SUBSCRIPTION,599,INR,Subscriptions
2026-09-02 09:00,ACME STREAMING SUBSCRIPTION,599,INR,Subscriptions
2026-07-05 12:00,KIRANA STORE,1200,INR,Groceries
2026-08-05 12:00,KIRANA STORE,1450,INR,Groceries
2026-09-05 12:00,KIRANA STORE,980,INR,Groceries
"""


def test_agent_weekly_attention_stops_for_approval(client, user):
    # give the agent some data first
    doc = upload(client, user["token"], "agent_txns.csv", DATA_CSV)
    wait_ready(client, user["token"], doc["id"])

    r = client.post("/api/v1/agent/run",
                    json={"request": "What needs my attention this week?"},
                    headers=auth(user["token"]))
    assert r.status_code == 200
    final = sse_final(r)
    run_id = final["run_id"]
    # weekly plan includes a SENSITIVE create_reminder step -> approval gate
    assert final["status"] == "WAITING_APPROVAL"

    # trace is visible with real steps
    r = client.get(f"/api/v1/agent/tasks/{run_id}", headers=auth(user["token"]))
    assert r.status_code == 200
    task = r.json()
    step_names = [s["name"] for s in task["steps"]]
    assert "intent_classification" in step_names
    assert any(n.startswith("approval_gate") for n in step_names)
    tool_steps = [s for s in task["steps"] if s["type"] == "TOOL" and s["status"] == "OK"]
    assert len(tool_steps) >= 4  # deadlines, search, subs, anomalies, report
    # tool steps carry real results
    assert any("deadlines" in json.dumps(s["result"]) for s in tool_steps)

    # pending approval exists
    r = client.get("/api/v1/approvals", headers=auth(user["token"]))
    pending = [a for a in r.json() if a["status"] == "PENDING" and a["run_id"] == run_id]
    assert len(pending) == 1
    ap_id = pending[0]["id"]
    assert pending[0]["risk_class"] == "SENSITIVE"

    # approve -> run completes, reminder created
    r = client.post(f"/api/v1/approvals/{ap_id}/approve", headers=auth(user["token"]))
    assert r.status_code == 200
    assert r.json()["status"] == "EXECUTED"
    r = client.get(f"/api/v1/agent/tasks/{run_id}", headers=auth(user["token"]))
    assert r.json()["status"] == "COMPLETED"
    assert r.json()["response_text"]


def test_agent_reject_path(client, user):
    r = client.post("/api/v1/agent/run",
                    json={"request": "What should I take care of this week?"},
                    headers=auth(user["token"]))
    final = sse_final(r)
    run_id = final["run_id"]
    r = client.get("/api/v1/approvals", headers=auth(user["token"]))
    pending = [a for a in r.json() if a["status"] == "PENDING" and a["run_id"] == run_id]
    assert len(pending) == 1
    ap_id = pending[0]["id"]
    r = client.post(f"/api/v1/approvals/{ap_id}/reject", headers=auth(user["token"]))
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED"
    r = client.get(f"/api/v1/agent/tasks/{run_id}", headers=auth(user["token"]))
    task = r.json()
    assert task["status"] == "COMPLETED"
    # the gated step is recorded as skipped, not executed
    gate = [s for s in task["steps"] if s["name"].startswith("approval_gate")]
    assert any(s["status"] == "SKIPPED" for s in gate)


def test_agent_rag_question_completes_directly(client, user):
    doc = upload(client, user["token"], "agent_note.txt",
                 "The office cat's name is Whiskers. The cat prefers salmon.")
    wait_ready(client, user["token"], doc["id"])
    r = client.post("/api/v1/agent/run",
                    json={"request": "What is the office cat's name?"},
                    headers=auth(user["token"]))
    final = sse_final(r)
    assert final["status"] == "COMPLETED"
    r = client.get(f"/api/v1/agent/tasks/{final['run_id']}", headers=auth(user["token"]))
    task = r.json()
    # no approval gates for a pure read-only RAG question
    assert not [s for s in task["steps"] if s["type"] == "GATE"]
    assert task["response_text"]


def test_agent_list_and_pagination(client, user):
    r = client.get("/api/v1/agent/tasks?limit=5", headers=auth(user["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3
    assert len(body["items"]) <= 5


def test_isolation_of_agent_runs(client, user, user2):
    r = client.get("/api/v1/agent/tasks", headers=auth(user2["token"]))
    assert r.status_code == 200
    assert r.json()["total"] == 0
