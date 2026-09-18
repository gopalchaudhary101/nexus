"""Feature engineering for transaction anomaly detection.

Features (per transaction):
    amount, log_amount, hour, weekday, month, day_of_month,
    merchant_freq (how often this merchant appears),
    new_merchant (1 if first appearance),
    merchant_z (robust z-score of amount vs that merchant's history)

Rationale: anomalies in personal statements are usually *relative* to the
user's own history (new merchant, unusual time, unusual amount), so
merchant-conditioned features carry most of the signal.
"""
from __future__ import annotations

from statistics import median


def build_features(transactions: list[dict]) -> tuple[list[dict], list[str]]:
    def key_of(t: dict) -> str:
        return t.get("merchant_key") or merchant_key(t["description"])

    merchant_dates: dict[str, list] = {}
    for t in transactions:
        merchant_dates.setdefault(key_of(t), []).append(t["date"])

    feats: list[dict] = []
    for t in transactions:
        d = t["date"]
        key = key_of(t)
        hist = [x["amount"] for x in transactions if key_of(x) == key]
        loc = median(hist)
        mad = median([abs(h - loc) for h in hist]) or 1e-6
        z = (t["amount"] - loc) / (1.4826 * mad)
        import math
        feats.append({
            "amount": t["amount"],
            "log_amount": math.log1p(max(t["amount"], 0)),
            "hour": d.hour if hasattr(d, "hour") else 12,
            "weekday": d.weekday(),
            "month": d.month,
            "day_of_month": d.day,
            "merchant_freq": len(merchant_dates[key]),
            "new_merchant": 1 if len(merchant_dates[key]) == 1 else 0,
            "merchant_z": max(min(z, 10.0), -10.0),
        })
    feature_names = ["amount", "log_amount", "hour", "weekday", "month",
                     "day_of_month", "merchant_freq", "new_merchant", "merchant_z"]
    return feats, feature_names


def merchant_key(description: str) -> str:
    from ..recurring.detector import normalize_merchant
    return normalize_merchant(description)
