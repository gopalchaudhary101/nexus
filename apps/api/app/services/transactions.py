"""Transaction CSV parsing + import."""
from __future__ import annotations

import json
from io import StringIO

from sqlalchemy import select

from ml.recurring.detector import normalize_merchant

from ..db.models import Merchant, Transaction


def _col(df, *names: str) -> str | None:
    lower = {c.lower().strip(): c for c in df.columns}
    for n in names:
        if n in lower:
            return lower[n]
    return None


def parse_transactions_csv(text: str) -> list[dict]:
    import pandas as pd

    df = pd.read_csv(StringIO(text))
    if df.empty:
        return []
    c_date = _col(df, "date", "txn date", "transaction date", "posted")
    c_desc = _col(df, "description", "desc", "merchant", "payee", "details", "memo")
    c_amt = _col(df, "amount", "amt", "amount (inr)", "amount (usd)", "value")
    c_cur = _col(df, "currency", "ccy")
    c_cat = _col(df, "category", "cat")
    if not (c_date and c_desc and c_amt):
        raise ValueError("CSV needs at least columns: date, description, amount")
    rows: list[dict] = []
    for _, r in df.iterrows():
        raw_date = str(r[c_date]).strip()
        fmt = "%Y-%m-%d %H:%M" if len(raw_date) >= 16 else None
        ts = pd.to_datetime(raw_date, errors="coerce", format=fmt)
        if pd.isna(ts):
            ts = pd.to_datetime(raw_date, errors="coerce", dayfirst=True)
        if pd.isna(ts):
            continue
        try:
            amount = float(str(r[c_amt]).replace(",", "").replace("₹", "").strip())
        except ValueError:
            continue
        desc = str(r[c_desc]).strip()
        if not desc:
            continue
        cur = "INR"
        if c_cur is not None and str(r[c_cur]).strip():
            cur = str(r[c_cur]).strip().upper()
        cat = ""
        if c_cat is not None:
            cat = str(r[c_cat]).strip()
        rows.append({
            "date": ts.to_pydatetime(),
            "description": desc,
            "amount": amount,
            "currency": cur,
            "category": cat,
            "merchant_key": normalize_merchant(desc),
        })
    return rows


def find_matching_subscription(db, user_id: str, merchant: str, frequency: str):
    """Exact (user, merchant, frequency) match first, then merchant-name
    containment (doc-derived 'Fitzone Gym' vs transaction-derived
    'Fitzone Gym Membership')."""
    from ..db.models import Subscription

    rows = db.execute(select(Subscription).where(
        Subscription.user_id == user_id, Subscription.frequency == frequency
    )).scalars().all()
    m = merchant.lower()
    for r in rows:
        if r.merchant.lower() == m:
            return r
    for r in rows:
        rm = r.merchant.lower()
        if len(m) > 3 and len(rm) > 3 and (m in rm or rm in m):
            return r
    return None


def refresh_subscriptions_for_user(db, user_id: str) -> list:
    """Detect recurring subscriptions from the user's full transaction
    history and upsert them. Called after any CSV import and available to
    seeds/jobs. Dedupes on (user, merchant, frequency) with name containment."""
    from datetime import date

    from ml.recurring import detect_subscriptions

    from ..db.models import Subscription

    txns = db.execute(select(Transaction).where(Transaction.user_id == user_id)).scalars().all()
    rows = [{"date": t.date, "description": t.description, "amount": t.amount,
             "currency": t.currency} for t in txns]
    if len(rows) < 3:
        return []
    subs = detect_subscriptions(rows, date.today())
    for s in subs:
        merchant = s.merchant.title()[:255]
        existing = find_matching_subscription(db, user_id, merchant, s.frequency)
        if existing is None:
            db.add(Subscription(
                user_id=user_id, merchant=merchant,
                raw_merchant=s.raw_merchant[:512], amount=s.amount,
                currency=s.currency, frequency=s.frequency,
                occurrences=s.occurrences, first_date=s.first_date,
                last_date=s.last_date, next_due=s.next_due,
                median_interval_days=s.median_interval_days,
                monthly_equivalent=s.monthly_equivalent,
                annualized_cost=s.annualized_cost, amount_cv=s.amount_cv,
                status=s.status,
                price_increase_json=json.dumps(s.price_increase),
                confidence=s.confidence, notes_json=json.dumps(s.notes),
                source="transactions",
            ))
        else:
            existing.occurrences = max(existing.occurrences, s.occurrences)
            existing.status = s.status
            existing.price_increase_json = json.dumps(s.price_increase)
            existing.notes_json = json.dumps(s.notes)
            existing.last_date = s.last_date
            existing.next_due = s.next_due
            existing.amount = s.amount
            existing.monthly_equivalent = s.monthly_equivalent
            existing.annualized_cost = s.annualized_cost
            existing.confidence = max(existing.confidence, s.confidence)
    db.commit()
    return subs


def import_transactions(db, user_id: str, rows: list[dict], source: str,
                        source_doc_id: str | None = None) -> int:
    n = 0
    for r in rows:
        m = db.execute(
            select(Merchant).where(Merchant.user_id == user_id,
                                   Merchant.normalized == r["merchant_key"])
        ).scalar_one_or_none()
        if m is None:
            m = Merchant(user_id=user_id, name=r["description"],
                         normalized=r["merchant_key"])
            db.add(m)
            db.flush()
        db.add(Transaction(
            user_id=user_id, merchant_id=m.id, date=r["date"],
            description=r["description"], amount=r["amount"],
            currency=r.get("currency", "INR"), category=r.get("category", ""),
            source=source, source_doc_id=source_doc_id,
        ))
        n += 1
    db.commit()
    return n
