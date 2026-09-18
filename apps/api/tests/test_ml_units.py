"""Unit tests for the ml/ package (framework-free)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from ml.anomaly import TransactionAnomalyDetector
from ml.evaluation.metrics import compute_metrics
from ml.extraction import classify_document, extract_amounts, extract_dates, extract_entities
from ml.extraction.classify import CATEGORIES
from ml.forecasting import forecast_monthly_spending
from ml.recurring import detect_subscriptions
from ml.risk import ScamClassifier, assess_message

TODAY = date(2026, 9, 17)


def _txns(base: date, desc: str, amount: float, n: int, interval: int,
          amount_fn=None) -> list[dict]:
    out = []
    for i in range(n):
        d = base + timedelta(days=interval * i)
        amt = amount_fn(i) if amount_fn else amount
        out.append({"date": d, "description": desc, "amount": amt,
                    "currency": "INR"})
    return out


# ── dates ───────────────────────────────────────────────────────────────

def test_date_formats():
    text = "expires on 14 March 2027 | valid until Mar 14, 2027 | 2027-03-14 | 14/03/2027 | due 14-03-27"
    vals = {d.value.isoformat() for d in extract_dates(text)}
    assert "2027-03-14" in vals
    assert len(extract_dates(text)) >= 4
    assert extract_dates("day 32 month 13") == []


# ── amounts ─────────────────────────────────────────────────────────────

def test_amounts():
    hits = extract_amounts("Amount due: INR 2,340. Total 1,25,000 and 799 INR per month, plus $1,299")
    vals = {h.value for h in hits}
    assert 2340.0 in vals
    assert 125000.0 in vals
    assert 799.0 in vals
    assert any(h.currency == "USD" for h in hits)


# ── entities ────────────────────────────────────────────────────────────

def test_entities():
    text = ("Contact support@acme.com or call +91 98765 43210. "
            "Pay at http://secure-bank-verify.co/login now. "
            "Policyholder: Alice Example.")
    ents = extract_entities(text)
    kinds = {e.kind for e in ents}
    assert "EMAIL" in kinds
    assert "URL" in kinds
    assert any(e.kind == "URL" and e.attrs.get("suspicious") for e in ents)
    assert any(e.kind == "PERSON" and "Alice" in e.value for e in ents)


# ── classification ──────────────────────────────────────────────────────

def test_classification():
    cat, conf, _ = classify_document("Insurance policy. Premium 18,500. Claims. Coverage. Exclusion clause.")
    assert cat == "INSURANCE"
    cat, _, _ = classify_document("Invoice #123. GSTIN: 29ABCDE1234F2Z5. Payment terms net 30.")
    assert cat == "INVOICE"
    assert classify_document("hello world")[0] in CATEGORIES


# ── recurring ───────────────────────────────────────────────────────────

def test_recurring_detection_and_price_increase():
    txns = _txns(date(2025, 3, 2), "ACME STREAMING SUBSCRIPTION", 599, 18, 30,
                 amount_fn=lambda i: 599 if i < 16 else 799)
    txns += _txns(date(2025, 3, 5), "KIRANA STORE", 1200, 18, 30)
    # a genuine one-off must NOT become a subscription
    txns.append({"date": date(2026, 6, 20), "description": "LAPTOP REPAIR NOVA",
                 "amount": 3800, "currency": "INR"})
    subs = detect_subscriptions(txns, TODAY)
    acme = next((s for s in subs if "acme" in s.merchant), None)
    assert acme is not None
    assert acme.frequency == "MONTHLY"
    assert acme.occurrences == 18
    assert acme.price_increase is not None
    assert acme.price_increase["from"] == 599
    assert acme.price_increase["to"] == 799
    assert acme.price_increase["pct"] > 30
    # recurring kirana IS a subscription; one-off laptop repair is not
    assert any("kirana" in s.merchant for s in subs)
    assert not any("laptop" in s.merchant for s in subs)


def test_recurring_lapsed_flag():
    txns = _txns(date(2026, 1, 12), "MUSIC HUB PREMIUM", 149, 5, 30)
    subs = detect_subscriptions(txns, TODAY)
    music = next((s for s in subs if "music" in s.merchant), None)
    assert music is not None
    assert music.status == "LAPSED"
    assert any("not a usage claim" in n for n in music.notes)


# ── anomaly ─────────────────────────────────────────────────────────────

def test_anomaly_flags_seeded_outliers():
    txns = []
    for i in range(60):
        txns.append({"date": date(2026, 1, 1) + timedelta(days=i * 2),
                     "description": "KIRANA STORE NEAR HOME",
                     "amount": 1000 + (i % 7) * 120, "currency": "INR"})
    txns.append({"date": date(2026, 8, 28), "description": "MYSTERY TRANSFER X",
                 "amount": 55000, "currency": "INR"})
    det = TransactionAnomalyDetector().fit(txns)
    res = {r.index: r for r in det.predict(txns)}
    flagged = [r for r in res.values() if r.label != "NORMAL"]
    assert any(r.index == len(txns) - 1 for r in flagged)
    top = res[len(txns) - 1]
    assert top.label == "HIGHLY_UNUSUAL"
    assert top.explanations
    assert all("why" in e for e in top.explanations)


def test_anomaly_insufficient_data():
    with pytest.raises(ValueError):
        TransactionAnomalyDetector().fit(
            [{"date": date(2026, 1, 1), "description": "X", "amount": 1.0,
              "currency": "INR"}] * 3)


# ── forecasting ─────────────────────────────────────────────────────────

def test_forecast_insufficient():
    fc = forecast_monthly_spending([{"date": datetime(2026, 8, 1), "amount": 100}],
                                   TODAY)
    assert fc.ok is False
    assert "Not enough historical data" in fc.message


def test_forecast_with_history():
    txns = []
    base = date(2025, 8, 1)
    for m in range(14):
        d = base + timedelta(days=30 * m)
        txns.append({"date": d, "amount": 20000 + m * 500, "description": "x"})
    fc = forecast_monthly_spending(txns, date(2026, 1, 31), horizon=3)
    assert fc.ok is True
    assert len(fc.points) == 3
    p = fc.points[0]
    assert p["lo"] <= p["value"] <= p["hi"]
    assert fc.trend_pct_mom is not None


# ── risk ────────────────────────────────────────────────────────────────

def test_risk_high_vs_legit():
    scam = ("URGENT: Your account will be suspended within 24 hours. Verify your "
            "password and OTP at http://secure-bank-verify.co/login. Do not tell anyone.")
    legit = "Your monthly statement for August is ready. Review it in the app."
    s = assess_message(scam)
    legit_rep = assess_message(legit)
    assert s.risk_level == "HIGH"
    assert legit_rep.risk_level == "LOW"
    assert s.score > legit_rep.score
    assert s.signals
    assert s.disclaimer


def test_risk_classifier_holdout_metrics():
    m = ScamClassifier().holdout_metrics()
    assert m["accuracy"] >= 0.8
    assert m["scam_recall"] >= 0.7
    assert m["n_test"] > 0


# ── evaluation metrics ──────────────────────────────────────────────────

def test_compute_metrics_empty():
    rep = compute_metrics([])
    assert rep["evaluated"] is False
    assert "Not yet evaluated" in rep["message"]


def test_compute_metrics_rows():
    rows = [
        {"precision_at_1": 1.0, "recall_at_5": 1.0, "citation_accuracy": 1.0,
         "answer_correctness": 1.0, "latency_ms": 10.0},
        {"precision_at_1": 0.0, "recall_at_5": 1.0, "citation_accuracy": 0.0,
         "answer_correctness": 0.0, "latency_ms": 30.0},
    ]
    rep = compute_metrics(rows)
    assert rep["evaluated"] is True
    assert rep["metrics"]["precision_at_1"] == 0.5
    assert rep["metrics"]["latency_ms_avg"] == 20.0
