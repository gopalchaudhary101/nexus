"""API test fixtures: isolated temp SQLite DB + test client.

The database URL is pointed at a temp file BEFORE the app settings are read,
so no test ever touches the dev database.
"""
from __future__ import annotations

import os
import tempfile
import time

import pytest

_TMPDIR = tempfile.mkdtemp(prefix="nexus-test-")
os.environ["NEXUS_DATABASE_URL"] = f"sqlite:///{_TMPDIR}/test.db"
os.environ["NEXUS_UPLOAD_DIR"] = _TMPDIR + "/uploads"
os.environ["NEXUS_SECRET_KEY"] = "test-secret-key"
os.environ["NEXUS_AUTH_RATE_LIMIT"] = "50"
os.environ["NEXUS_LLM_PROVIDER"] = "mock"

from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # db/session.py caches the engine/session factory as a process-global
    # singleton (correct for a single production process). If another test
    # module built its own TestClient earlier in this same pytest process
    # (e.g. tests/test_e2e.py), that singleton would still point at *its*
    # temp database, and init_db() no-ops when an engine already exists —
    # so without resetting here, this fixture would silently run against
    # the wrong database instead of the one configured above.
    import app.db.session as sess
    if sess._engine is not None:
        sess._engine.dispose()
        sess._engine = None
        sess._SessionLocal = None
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def user(client):
    email = "alice@example.com"
    r = client.post("/api/v1/auth/register",
                    json={"email": email, "password": "supersecret1",
                          "name": "Alice"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["access_token"], "user": data["user"]}


@pytest.fixture(scope="session")
def user2(client):
    email = "bob@example.com"
    r = client.post("/api/v1/auth/register",
                    json={"email": email, "password": "supersecret2",
                          "name": "Bob"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["access_token"], "user": data["user"]}


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def upload(client, tok: str, filename: str, content: str | bytes) -> dict:
    data = content.encode() if isinstance(content, str) else content
    r = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, data, "application/octet-stream")},
        headers=auth(tok),
    )
    assert r.status_code == 202, r.text
    return r.json()


def wait_ready(client, tok: str, doc_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/documents/{doc_id}", headers=auth(tok))
        assert r.status_code == 200, r.text
        doc = r.json()
        if doc["status"] in ("READY", "FAILED"):
            return doc
        time.sleep(0.3)
    raise TimeoutError(f"Document {doc_id} not ready in {timeout}s")


def sse_final(r) -> dict:
    """Parse the last SSE data line of a streamed agent response."""
    last = {}
    for line in r.text.splitlines():
        if line.startswith("data: "):
            last = __import__("json").loads(line[6:])
    return last


INSURANCE_TXT = """Sentinel Insurance — Policy Summary

Policy Number: NEX-1234
Policyholder: Alice Example
Provider: Sentinel Insurance Ltd.
Plan: Comprehensive Health, Sum Assured INR 5,00,000.
Coverage start date: 1 January 2026.
The policy expires on 10 February 2027, unless renewed.
The annual premium is INR 12,000, payable yearly.
The renewal premium payment is due on 20 September 2026.
"""
