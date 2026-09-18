"""Recurring-payment / subscription detection.

Input
    Transaction records (date, description, amount, currency).

Method
    1. Normalise merchant names from descriptions (strip digits, generic tokens).
    2. Group transactions by normalised merchant; require >= 3 occurrences.
    3. Compute intervals between successive payments; classify by median:
         WEEKLY ~7d (±4) | MONTHLY ~30d (±6) | QUARTERLY ~90d (±12) | YEARLY ~365d (±20)
    4. Amount stability via coefficient of variation of the last 3 payments.
    5. Derive monthly equivalent, annualised cost, next due date, price increase.

Honesty rules (per product spec)
    - "unused / probably unneeded" is NEVER claimed here: there is no usage
      signal in transactions. Lapsed subscriptions (no payment > 2.5 intervals)
      are reported as LAPSED with a factual note only.
    - Every candidate carries a confidence in [0, 1].
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from statistics import mean, median, pstdev

from ..extraction.dates import _expand_year  # noqa: F401  (kept for API stability)

_DROP = {
    "the", "a", "an", "of", "for", "and", "to", "at", "by", "with", "your", "our",
    "payment", "paid", "billed", "bill", "invoice", "receipt", "charge", "debit",
    "credit", "transaction", "txn", "subscription", "sub", "monthly", "annual",
    "quarterly", "renewal", "renew", "fee", "amount", "due", "net", "total",
    "refund", "auto", "plan", "direct", "card", "upi", "ims",
}


def normalize_merchant(description: str) -> str:
    s = description.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if t not in _DROP and not t.isdigit()]
    return " ".join(toks[:4]).strip()


@dataclass
class SubscriptionCandidate:
    merchant: str
    raw_merchant: str
    amount: float                 # latest amount
    currency: str
    frequency: str                # WEEKLY | MONTHLY | QUARTERLY | YEARLY
    occurrences: int
    first_date: date
    last_date: date
    median_interval_days: float
    next_due: date
    monthly_equivalent: float
    annualized_cost: float
    amount_cv: float
    status: str                   # ACTIVE | LAPSED
    price_increase: dict | None = None
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


def _classify_interval(days: float) -> str | None:
    for name, center, tol in (("WEEKLY", 7, 4), ("MONTHLY", 30, 6),
                              ("QUARTERLY", 90, 14), ("YEARLY", 365, 25)):
        if abs(days - center) <= tol:
            return name
    return None


def detect_subscriptions(transactions: list[dict], today: date) -> list[SubscriptionCandidate]:
    groups: dict[str, list[dict]] = {}
    for t in transactions:
        if t.get("amount", 0) <= 0:
            continue
        key = normalize_merchant(t["description"])
        if len(key) < 3:
            continue
        groups.setdefault(key, []).append(t)

    def _as_date(x):
        return x.date() if hasattr(x, "hour") else x

    out: list[SubscriptionCandidate] = []
    for key, txns in groups.items():
        txns = sorted(txns, key=lambda t: t["date"])
        if len(txns) < 3:
            continue
        for t in txns:
            t["date"] = _as_date(t["date"])
        dates = [t["date"] for t in txns]
        intervals = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        med = median(intervals)
        frequency = _classify_interval(med)
        if frequency is None:
            continue
        # regularity: stdev of intervals vs median
        reg = pstdev(intervals) / med if med > 0 else 0.0
        amounts = [t["amount"] for t in txns]
        cv = (pstdev(amounts[-3:]) / (mean(amounts[-3:]) or 1.0))
        last = txns[-1]
        next_due = date.fromordinal(last["date"].toordinal() + int(round(med)))
        lapsed = (today - last["date"]).days > 2.5 * med
        monthly_eq = amounts[-1] / (med / 30.44)
        price_inc = None
        if len(amounts) >= 4:
            base = float(median(amounts[:-2]))
            if base > 0 and amounts[-1] > 1.05 * base:
                price_inc = {
                    "from": round(base, 2),
                    "to": amounts[-1],
                    "pct": round((amounts[-1] / base - 1) * 100, 1),
                    "date": last["date"].isoformat(),
                }
        conf = min(0.95, 0.4 + 0.06 * len(txns))
        if reg > 0.5:
            conf -= 0.15
        if cv > 0.25:
            conf -= 0.15
        conf = max(0.2, round(conf, 2))
        notes = []
        if lapsed:
            notes.append("No payment observed for >2.5 billing cycles — verify whether still wanted (not a usage claim).")
        if price_inc:
            notes.append(f"Price increased {price_inc['pct']}% on {price_inc['date']}.")
        out.append(SubscriptionCandidate(
            merchant=key, raw_merchant=last["description"], amount=amounts[-1],
            currency=last.get("currency", "INR"), frequency=frequency,
            occurrences=len(txns), first_date=dates[0], last_date=last["date"],
            median_interval_days=med, next_due=next_due,
            monthly_equivalent=round(monthly_eq, 2),
            annualized_cost=round(monthly_eq * 12, 2), amount_cv=round(cv, 3),
            status="LAPSED" if lapsed else "ACTIVE", price_increase=price_inc,
            confidence=conf, notes=notes,
        ))
    out.sort(key=lambda c: c.annualized_cost, reverse=True)
    return out
