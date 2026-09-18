"""Regression test for a race in the ingestion pipeline's get-or-create
helpers (knowledge-graph entities, deadlines, merchants).

The background job runner processes documents with >=2 worker threads
(core/config.py: worker_threads=2). Two documents for the same user can
therefore be ingested at the same instant, and each ingestion upserts a
singleton "USER" knowledge-graph node via services.graph.upsert_entity().
Before the fix, that helper was a plain check-then-insert with no unique
constraint backing it: two threads could both miss the SELECT and both
INSERT, leaving duplicate (user_id, kind, name) rows. Any later lookup of
that node (e.g. building the KnowledgeEntity used as the graph's OWNS/
MENTIONS source) then raised sqlalchemy.exc.MultipleResultsFound, which
services.ingest.run_ingestion caught and surfaced as a FAILED document.

This reproduced intermittently (~1 in 5-10 runs) via the full E2E test.
Uploading several documents back-to-back reproduces the same worker-pool
race far more reliably in isolation.
"""
from __future__ import annotations

from .conftest import auth, upload, wait_ready


def test_concurrent_ingestion_does_not_duplicate_graph_nodes(client, user2):
    tok = user2["token"]
    docs = [
        upload(client, tok, f"note_{i}.txt",
               f"Reminder: pay invoice #{i} due on 2027-0{(i % 9) + 1}-15.")["id"]
        for i in range(8)
    ]
    for doc_id in docs:
        d = wait_ready(client, tok, doc_id, timeout=30.0)
        assert d["status"] == "READY", d.get("status_detail")

    r = client.get("/api/v1/insights/graph", headers=auth(tok))
    assert r.status_code == 200
    nodes = r.json()["nodes"]
    user_nodes = [n for n in nodes if n["kind"] == "USER"]
    assert len(user_nodes) == 1, f"expected exactly one USER node, got {user_nodes}"
