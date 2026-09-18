"""Lightweight entity extraction (regex-based, confidence-scored).

Kinds: EMAIL, PHONE, URL, DOMAIN, MERCHANT, PERSON, ACCOUNT_REF
Every entity carries the evidence span so downstream UIs can show *why*.
Regex extraction is deliberately conservative: low-precision candidates
(e.g. PERSON) are scored low and only surfaced as "possible".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:(?<!\d)\+?\d[\d\s\-]{7,14}\d)(?!\d)")
URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+", re.I)
GENERIC_MERCHANT_TOKENS = {
    "the", "a", "an", "of", "for", "and", "to", "at", "by", "with", "your", "our",
    "payment", "paid", "billed", "bill", "invoice", "receipt", "charge", "debit",
    "credit", "transaction", "txn", "subscription", "monthly", "annual", "auto",
    "renewal", "renew", "fee", "amount", "due", "net", "total", "refund",
}


@dataclass
class Entity:
    kind: str
    value: str
    confidence: float
    evidence: str
    start: int = 0
    end: int = 0
    attrs: dict = field(default_factory=dict)


def _domain_from_url(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url, re.I)
    return m.group(1).lower().split(":")[0] if m else url


def extract_entities(text: str) -> list[Entity]:
    out: list[Entity] = []

    for m in EMAIL_RE.finditer(text):
        out.append(Entity("EMAIL", m.group(0), 0.97, f"pattern:email @ {m.start()}",
                          m.start(), m.end()))

    for m in PHONE_RE.finditer(text):
        v = m.group(0).strip()
        digits = re.sub(r"\D", "", v)
        if len(digits) < 8:
            continue
        out.append(Entity("PHONE", v, 0.7, f"pattern:phone near '{text[max(0, m.start()-20):m.end()+5].strip()[:40]}'",
                          m.start(), m.end()))

    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:")
        dom = _domain_from_url(url)
        tld = dom.rsplit(".", 1)[-1]
        risky = (
            not url.lower().startswith("https")
            or tld in {"co", "info", "xyz", "top", "click", "link", "pw", "cc", "gq", "tk", "ru", "cn"}
            or re.match(r"^\d+\.\d+\.\d+\.\d+$", dom) is not None
            or any(short in dom for short in ("bit.ly", "t.co", "goo.gl", "tinyurl"))
        )
        out.append(Entity("URL", url, 0.9, "pattern:url", m.start(), m.end(),
                          attrs={"domain": dom, "tld": tld, "suspicious": risky}))
        out.append(Entity("DOMAIN", dom, 0.9, "derived from URL", m.start(), m.end(),
                          attrs={"tld": tld, "suspicious": risky}))

    merchant_ctx = re.compile(
        r"(?i:(?:billed\s+by|paid\s+to|merchant|provider|company|organisation|issued\s+by))\s*"
        r":?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})",
    )
    for m in merchant_ctx.finditer(text):
        name = m.group(1).strip()
        if any(w in GENERIC_MERCHANT_TOKENS for w in name.lower().split()):
            continue
        out.append(Entity("MERCHANT", name, 0.6, f"context: '{m.group(0)[:40]}'", m.start(), m.end()))

    person_ctx = re.compile(
        r"(?i:(?:named|name\s+of|policyholder|applicant|employee|payee|attention|attn|passenger|tenant|landlord))\s*"
        r":?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    )
    for m in person_ctx.finditer(text):
        out.append(Entity("PERSON", m.group(1).strip(), 0.55, f"context: '{m.group(0)[:40]}'",
                          m.start(), m.end()))

    for m in re.finditer(r"\b(?:A/C|A/c|Account|Acc)\.?\s*(?:no\.?|number)?\s*[:#]?\s*([0-9A-Za-z\-]{6,24})\b", text, re.I):
        out.append(Entity("ACCOUNT_REF", m.group(1), 0.6, "context: account reference", m.start(), m.end()))

    out.sort(key=lambda e: e.start)
    return out
