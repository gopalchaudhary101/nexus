"""Data-science pipeline tests through the API: subscriptions, anomalies,
deadlines, forecast (with mandatory insufficient-data behaviour)."""
from __future__ import annotations

from .conftest import auth, sse_final, upload, wait_ready

CSV_SMALL = """date,description,amount,currency,category
2025-06-02 09:00,ZETA STREAMING SUBSCRIPTION,599,INR,Subscriptions
2025-07-02 09:00,ZETA STREAMING SUBSCRIPTION,599,INR,Subscriptions
2025-08-02 09:00,ZETA STREAMING SUBSCRIPTION,599,INR,Subscriptions
2025-09-02 09:00,ZETA STREAMING SUBSCRIPTION,699,INR,Subscriptions
2025-10-02 09:00,ZETA STREAMING SUBSCRIPTION,699,INR,Subscriptions
2025-11-02 09:00,ZETA STREAMING SUBSCRIPTION,699,INR,Subscriptions
2025-06-10 09:00,ZETA STREAMING SUBSCRIPTION,599,INR,Subscriptions
2025-06-05 12:00,KIRANA STORE,1200,INR,Groceries
2025-07-05 12:00,KIRANA STORE,1450,INR,Groceries
2025-08-05 12:00,KIRANA STORE,980,INR,Groceries
2025-09-05 12:00,KIRANA STORE,1320,INR,Groceries
2025-10-05 12:00,KIRANA STORE,1510,INR,Groceries
2025-11-05 12:00,KIRANA STORE,1100,INR,Groceries
2025-09-30 23:40,MYSTERY TRANSFER X,55000,INR,Transfer
2025-10-12 01:10,WEIRD PAY PORTAL,23000,INR,Other
"""


def test_forecast_insufficient_data(client, user2):
    r = client.get("/api/v1/insights/forecast", headers=auth(user2["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Not enough historical data" in body["message"]


def test_subscriptions_anomalies_deadlines(client, user):
    doc = upload(client, user["token"], "txns.csv", CSV_SMALL)
    wait_ready(client, user["token"], doc["id"])

    # subscriptions (recurring detection)
    r = client.get("/api/v1/insights/subscriptions", headers=auth(user["token"]))
    assert r.status_code == 200
    subs = {s["merchant"]: s for s in r.json()}
    assert "Zeta Streaming" in subs, list(subs)
    zeta = subs["Zeta Streaming"]
    assert zeta["frequency"] == "MONTHLY"
    assert zeta["amount"] == 699
    assert zeta["price_increase"] is not None
    assert zeta["price_increase"]["pct"] > 5

    # anomalies
    r = client.post("/api/v1/agent/run",
                    json={"request": "Show unusual transactions"},
                    headers=auth(user["token"]))
    assert r.status_code == 200
    final = sse_final(r)
    assert final["status"] in ("COMPLETED", "WAITING_APPROVAL")
    r = client.get("/api/v1/insights/anomalies", headers=auth(user["token"]))
    assert r.status_code == 200
    anoms = r.json()
    assert len(anoms) >= 2
    labels = {a["description"]: a["label"] for a in anoms}
    assert "MYSTERY TRANSFER X" in labels
    top = max(anoms, key=lambda a: a["score"])
    assert top["description"] == "MYSTERY TRANSFER X"
    assert top["note"].lower().startswith("anomaly")

    # deadlines (from the earlier insurance doc if present, else empty ok)
    r = client.get("/api/v1/insights/deadlines", headers=auth(user["token"]))
    assert r.status_code == 200
    for d in r.json():
        assert d["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert "days_remaining" in d


def test_risk_engine_endpoints(client, user):
    scam = ("URGENT: Your account will be suspended within 24 hours. Send your "
            "OTP and password to +1 555 0199 now. Do not tell anyone.")
    r = client.post("/api/v1/risk/analyze", json={"text": scam},
                    headers=auth(user["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["risk_level"] == "HIGH"
    assert body["score"] >= 0.6
    assert len(body["signals"]) >= 2
    assert body["disclaimer"]

    legit = "Your monthly statement for August is ready. Review it in the app."
    r = client.post("/api/v1/risk/analyze", json={"text": legit},
                    headers=auth(user["token"]))
    body = r.json()
    assert body["risk_level"] in ("LOW", "MEDIUM")
    assert body["score"] < 0.5


def test_risk_requires_input(client, user):
    r = client.post("/api/v1/risk/analyze", json={}, headers=auth(user["token"]))
    assert r.status_code == 400


