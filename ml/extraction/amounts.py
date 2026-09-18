"""Currency amount extraction (INR first, then USD/EUR/GBP).

Handles:  ₹799  |  Rs. 1,250  |  INR 18,500.00  |  $1,299  |  2,340 due
Indian digit grouping (12,50,000) is normalised by stripping commas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_CURRENCY_RE = re.compile(
    r"(?:₹|Rs\.?|INR|\$|€|£)\s?([0-9][0-9,]{0,12}(?:\.[0-9]{1,2})?)",
    re.I,
)
_TRAILING_CURRENCY_RE = re.compile(
    r"\b([0-9][0-9,]{0,12}(?:\.[0-9]{1,2})?)\s*(?:INR|Rs\.?|USD|EUR|GBP)",
    re.I,
)
_BARE_RES = [
    # Western grouping: 1,234 / 12,345 / 1,234,567
    re.compile(r"\b([0-9]{1,3}(?:,[0-9]{3}){1,3}(?:\.[0-9]{1,2})?)\b"),
    # Indian grouping: 12,50,000 (ends in ,XXX)
    re.compile(r"\b([0-9]{1,2}(?:,[0-9]{2}){1,2},[0-9]{3}(?:\.[0-9]{1,2})?)\b"),
]


@dataclass(frozen=True)
class AmountHit:
    value: float
    currency: str
    raw: str
    start: int
    end: int


def _parse(raw: str) -> float | None:
    cleaned = raw.replace(",", "")
    try:
        v = Decimal(cleaned)
    except InvalidOperation:
        return None
    return float(v)


def extract_amounts(text: str) -> list[AmountHit]:
    hits: list[AmountHit] = []
    spans: set[tuple[int, int]] = set()
    for m in _CURRENCY_RE.finditer(text):
        v = _parse(m.group(1))
        if v is None:
            continue
        cur = "INR" if (text[m.start():m.start() + 2] in ("₹",) or
                        re.match(r"(?i)^(rs|inr)", text[m.start():m.start() + 4])) else \
              ("USD" if text[m.start()] == "$" else "EUR" if text[m.start()] == "€" else "GBP")
        span = (m.start(), m.end())
        spans.add(span)
        hits.append(AmountHit(value=v, currency=cur, raw=m.group(0), start=span[0], end=span[1]))
    for m in _TRAILING_CURRENCY_RE.finditer(text):
        v = _parse(m.group(1))
        if v is None:
            continue
        tail = m.group(0)[len(m.group(1)):].strip().lower()
        cur = "INR" if tail.startswith(("inr", "rs")) else \
              ("USD" if tail.startswith("usd") else "EUR" if tail.startswith("eur") else "GBP")
        span = (m.start(), m.end())
        spans.add(span)
        hits.append(AmountHit(value=v, currency=cur, raw=m.group(0), start=span[0], end=span[1]))
    for pat in _BARE_RES:
        for m in pat.finditer(text):
            span = (m.start(), m.end())
            if span in spans:
                continue
            v = _parse(m.group(1))
            if v is None:
                continue
            spans.add(span)
            hits.append(AmountHit(value=v, currency="UNSPECIFIED", raw=m.group(0),
                                  start=span[0], end=span[1]))
    hits.sort(key=lambda h: h.start)
    return hits
