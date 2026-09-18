"""Date extraction with explicit format coverage.

Formats handled:
    14 March 2027 | March 14, 2027 | Mar 14 2027 | 2027-03-14 | 14/03/2027 | 14-03-27

Ambiguity policy
    Two-digit years are expanded (>=70 -> 19xx, else 20xx).
    Slash/dash numeric dates default to DAY-first (primary user base: IN).
Invalid dates (month 13, day 32, ...) are dropped, never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})[a-z]*,?\s+(\d{{4}})\b", re.I), "dmy_named"),
    (re.compile(rf"\b({_MONTH_ALT})[a-z]*\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I), "mdy_named"),
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b"), "dmy_num"),
]


@dataclass(frozen=True)
class DateHit:
    value: date
    raw: str
    start: int
    end: int


def _make(y: int, m: int, d: int) -> date | None:
    if not (1 <= m <= 12):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _expand_year(y: int) -> int:
    return 1900 + y if y >= 70 else 2000 + y


def extract_dates(text: str) -> list[DateHit]:
    hits: list[DateHit] = []
    seen: set[tuple[int, int]] = set()
    for pattern, order in _PATTERNS:
        for m in pattern.finditer(text):
            a, b, c = m.group(1), m.group(2), m.group(3)
            if order == "dmy_named":          # 14 March 2027
                d, m_, y = int(a), _MONTHS.get(b.lower()), int(c)
            elif order == "mdy_named":        # March 14, 2027
                m_, d, y = _MONTHS.get(a.lower()), int(b), int(c)
            elif order == "ymd":              # 2027-03-14
                y, m_, d = int(a), int(b), int(c)
            else:                             # 14/03/2027 or 14-03-27
                d, m_, y = int(a), int(b), _expand_year(int(c))
            if m_ is None:
                continue
            val = _make(y, m_, d)
            if val is None:
                continue
            span = (m.start(), m.end())
            if span in seen:
                continue
            seen.add(span)
            hits.append(DateHit(value=val, raw=m.group(0), start=span[0], end=span[1]))
    hits.sort(key=lambda h: h.start)
    return hits
