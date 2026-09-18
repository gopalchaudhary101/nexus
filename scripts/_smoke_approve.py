#!/usr/bin/env python3
"""Live approval round-trip against the running API (verification script)."""
import json
import urllib.request

B = "http://localhost:8000/api/v1"


def call(method, path, body=None, tok=None):
    req = urllib.request.Request(B + path, method=method)
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data) as r:
        return json.loads(r.read().decode())


tok = call("POST", "/auth/login", {"email": "demo@nexus.dev",
                                   "password": "nexus-demo-2026"})["access_token"]
approvals = call("GET", "/approvals", tok=tok)
pending = [a for a in approvals if a["status"] == "PENDING"]
assert pending, "no pending approval found"
a = pending[0]
print(f"pending: tool={a['tool']} risk={a['risk_class']} args={a['args']}")
res = call("POST", f"/approvals/{a['id']}/approve", tok=tok)
print(f"approve -> status={res['status']} result={res['result']}")

runs = call("GET", "/agent/tasks?limit=5", tok=tok)["items"]
run = next(r for r in runs if r["id"] == a["run_id"])
steps = run["steps"]
print(f"run {run['id']}: status={run['status']} steps={len(steps)}")
gate = [s for s in steps if s["type"] == "GATE"]
print("gate step:", [(g["name"], g["status"]) for g in gate])
print("last tools:", [s["name"] for s in steps if s["type"] == "TOOL"][-3:])
print("response head:", run["response_text"][:180].replace("\n", " | "))

# a fresh agent run end-to-end (SSE not used here; verify via tasks)
print("\nALL OK" if run["status"] == "COMPLETED" else "NOT COMPLETED")
