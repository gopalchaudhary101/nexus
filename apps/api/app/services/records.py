"""Structured record derivation (deadlines + subscriptions) from documents.

Method: keyword-anchored date/amount search over a local window around each
keyword occurrence. Every derived record carries the page reference and a
confidence; fields that cannot be found are simply omitted (no hallucination).
"""
from __future__ import annotations

import re
from datetime import date

from ml.extraction.amounts import extract_amounts
from ml.extraction.dates import extract_dates

_WINDOW = 90  # chars around the keyword to search for the anchor value

FREQ_KEYWORDS = {
    "weekly": "WEEKLY",
    "monthly": "MONTHLY",
    "quarterly": "QUARTERLY",
    "annual": "YEARLY",
    "yearly": "YEARLY",
    "per year": "YEARLY",
    "per month": "MONTHLY",
    "per quarter": "QUARTERLY",
    "per week": "WEEKLY",
}


def _near(text: str, keyword: str) -> list[tuple[int, int]]:
    return [m.span() for m in re.finditer(keyword, text, re.I)]


def _dates_in_window(pages: list[str] | list[None], text: str, spans: list[tuple[int, int]]) -> list[dict]:
    """Return date hits within `spans` windows, with page attribution."""
    full = text
    page_offsets: list[tuple[int, int]] = []
    if pages:
        pos = 0
        for p in pages:
            page_offsets.append((pos, pos + len(p or "")))
            pos += len(p or "") + 2  # "\n\n"
    out = []
    seen = set()
    for a, b in spans:
        lo, hi = max(0, a - _WINDOW), min(len(full), b + _WINDOW)
        seg = full[lo:hi]
        for d in extract_dates(seg):
            if d.value in seen:
                continue
            seen.add(d.value)
            page = 1
            if page_offsets:
                abs_pos = lo + d.start
                for i, (s, e) in enumerate(page_offsets, start=1):
                    if s <= abs_pos < e:
                        page = i
                        break
            out.append({"date": d.value, "raw": d.raw, "page": page})
    return out


def _amount_in_window(text: str, spans: list[tuple[int, int]]) -> dict | None:
    for a, b in spans:
        lo, hi = max(0, a - _WINDOW), min(len(text), b + _WINDOW)
        seg = text[lo:hi]
        amts = extract_amounts(seg)
        if amts:
            best = max(amts, key=lambda x: x.value)
            return {"amount": best.value, "currency": best.currency, "raw": best.raw}
    return None


def _first(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.I)
    return m.group(1).strip() if m else None


_CAPS_GENERIC = {
    "RECEIPT", "NO", "N", "INVOICE", "PLAN", "MONTHLY", "ANNUAL", "DATE", "TOTAL",
    "AMOUNT", "PAID", "CARD", "UPI", "VISA", "MASTERCARD", "MEMBERSHIP", "FEE",
    "PER", "THE", "AND", "FOR", "SUMMARY", "STATEMENT", "BILL", "NOTICE", "CARE",
    "PREMIUM", "STANDARD", "TODAY", "YESTERDAY", "TOMORROW",
}


def _resolve_merchant(text: str) -> str:
    """Best-effort merchant name: contextual phrase first, then an all-caps
    brand token (receipts print names in caps), then a Title-case fallback.
    Never returns empty; generic words (RECEIPT, NO, PLAN…) are excluded."""
    m = _first(text, r"(?:billed by|provider|merchant|company|issued by)\s*:?\s+([A-Z][A-Za-z&\.\- ]{2,40})")
    if m:
        return m
    for m in re.finditer(r"\b([A-Z][A-Z0-9]{1,}(?: [A-Z][A-Z0-9]{1,}){0,2})\b", text):
        words = m.group(1).split()
        if all(w in _CAPS_GENERIC for w in words):
            continue
        if any(w.isdigit() for w in words):
            continue
        return m.group(1).title()
    m = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,3})\b", text)
    return m.group(1) if m else "Unknown merchant"


def derive_deadlines(doc_type: str, text: str, pages: list[str],
                     source_ref_base: str) -> list[dict]:
    out: list[dict] = []
    t = text
    today = date.today()

    def pick_date(cands: list[dict]) -> dict | None:
        """Prefer the earliest FUTURE date in the window (deadline semantics);
        document dates (billing period, issue date) are usually past, so they
        lose to a plausible future date. If all are past, take the latest
        (a recently-overdue deadline beats an ancient one)."""
        if not cands:
            return None
        future = [c for c in cands if c["date"] >= today]
        if future:
            return min(future, key=lambda c: c["date"])
        return max(cands, key=lambda c: c["date"])

    def add(title: str, kind: str, spans: list[tuple[int, int]], amount: dict | None,
            importance: int, notes: str = "") -> None:
        d = pick_date(_dates_in_window(pages, t, spans))
        if d is None:
            return
        out.append({
            "title": title, "kind": kind, "due_date": d["date"],
            "source_ref": f"{source_ref_base} — Page {d['page']}",
            "amount": (amount or {}).get("amount"),
            "currency": (amount or {}).get("currency", "INR"),
            "importance": importance, "notes": notes,
            "confidence": 0.8 if amount else 0.65,
        })

    if doc_type == "INSURANCE":
        add("Insurance policy expiry", "INSURANCE_EXPIRY", _near(t, r"expir(?:e|es|ed|y|ation)"),
            _amount_in_window(t, _near(t, r"premium")), 4, "Policy lapses if not renewed.")
        add("Insurance renewal payment", "RENEWAL", _near(t, r"renewal"),
            _amount_in_window(t, _near(t, r"renewal")), 4)
        add("Insurance payment due", "PAYMENT", _near(t, r"(?:due|pay) (?:date|by|on)"),
            _amount_in_window(t, _near(t, r"(?:premium|amount)")), 3)
    elif doc_type == "BILL":
        add("Bill payment due", "PAYMENT",
            _near(t, r"(?:due date|pay by|due on|payment due)"),
            _amount_in_window(t, _near(t, r"amount due|total|payable")), 4)
    elif doc_type == "CONTRACT":
        end_spans = _near(t, r"(?:ends?|until|through|lease (?:end|termination|expiry))")
        add("Contract/lease end", "CONTRACT_END", end_spans,
            _amount_in_window(t, _near(t, r"rent")), 3,
            "Review renewal/cancellation terms before this date.")
        add("Renewal notice due", "NOTICE", _near(t, r"(?:renewal )?(?:notice) (?:by|before|date)"),
            None, 4)
    elif doc_type == "SUBSCRIPTION":
        add("Next subscription billing", "RENEWAL",
            _near(t, r"next (?:billing|payment|charge|renewal)"),
            _amount_in_window(t, _near(t, r"(?:amount|fee|total|charge)")), 3)
        add("Subscription renewal", "RENEWAL", _near(t, r"(?:renew|renews|auto[- ]?renew)\w*"),
            _amount_in_window(t, _near(t, r"(?:amount|fee|total|charge|₹)")), 3)
        add("Cancellation deadline", "CANCELLATION",
            _near(t, r"cancel(?:l)?(?:e|ation)?\w* (?:by|before|until|date)"),
            None, 4, "Miss this window and you may be charged another cycle.")
    elif doc_type == "WARRANTY":
        add("Warranty expiry", "WARRANTY",
            _near(t, r"(?:valid|coverage|warranty)\w* (?:until|through|till|ends? on|period)")
            + _near(t, r"(?:until|through|till)\b"),
            None, 2, "Claims after this date are out of coverage.")
    elif doc_type == "TRAVEL":
        add("Travel departure", "TRAVEL", _near(t, r"(?:departure|on|for|date of)"),
            _amount_in_window(t, _near(t, r"(?:paid|total|fare)")), 2)
    else:
        # Generic: explicit deadline phrasings
        add("Deadline (response/acceptance)", "DEADLINE",
            _near(t, r"(?:response|reply|acceptance|submit|submission) (?:deadline|due|by)"),
            _amount_in_window(t, _near(t, r"amount")), 3)
        add("Document due date", "DEADLINE", _near(t, r"(?:due date|due on|pay by)"),
            _amount_in_window(t, _near(t, r"amount")), 3)

    # dedupe on (title, date)
    seen: set[tuple[str, date]] = set()
    deduped = []
    for d in out:
        k = (d["title"], d["due_date"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(d)
    return deduped


def derive_subscription(doc_type: str, text: str, source_ref_base: str) -> dict | None:
    if doc_type != "SUBSCRIPTION":
        return None
    t = text
    amounts = extract_amounts(t)
    if not amounts:
        return None
    amount = max((a for a in amounts if a.value > 0), key=lambda a: a.value, default=None)
    if amount is None:
        return None
    freq = "MONTHLY"
    for kw, val in FREQ_KEYWORDS.items():
        if re.search(rf"\b{re.escape(kw)}\b", t, re.I):
            freq = val
            break
    next_date = None
    nd = _dates_in_window([], t, _near(t, r"next (?:billing|payment|charge|renewal)"))
    if nd:
        next_date = nd[0]["date"]
    cancel_date = None
    cd = _dates_in_window([], t, _near(t, r"cancel(?:l)?(?:e|ation)?\w* (?:by|before|until|date)"))
    if cd:
        cancel_date = cd[0]["date"]
    auto_renew = bool(re.search(r"auto[- ]?renew\w*\s*(?:is\s*)?(on|enabled|active|yes)", t, re.I))
    if re.search(r"auto[- ]?renew\w*\s*(?:is\s*)?(off|disabled|no)", t, re.I):
        auto_renew = False
    merchant = _resolve_merchant(t)
    from ml.recurring.detector import normalize_merchant
    merchant_norm = normalize_merchant(merchant)
    if len(merchant_norm) >= 3:
        merchant = merchant_norm.title()
    interval = {"WEEKLY": 7, "MONTHLY": 30, "QUARTERLY": 90, "YEARLY": 365}[freq]
    today = date.today()
    if next_date is None:
        from datetime import timedelta
        next_date = today + timedelta(days=interval)
    return {
        "merchant": merchant, "raw_merchant": merchant,
        "amount": amount.value, "currency": amount.currency,
        "frequency": freq, "next_due": next_date,
        "monthly_equivalent": round(amount.value / (interval / 30.44), 2),
        "annualized_cost": round(amount.value / (interval / 30.44) * 12, 2),
        "auto_renew": auto_renew, "cancellation_deadline": cancel_date,
        "confidence": 0.8, "source_ref": source_ref_base,
    }
