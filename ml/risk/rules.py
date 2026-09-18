"""Rule-based scam signal detection.

Each signal is a named heuristic with a weight in [0, 1] and an evidence
snippet. Weights are hand-set priors (not calibrated on labeled fraud data);
the calibrated component of the final score comes from the Naive Bayes
classifier (see classifier.py). Thresholds map the fused score to
LOW / MEDIUM / HIGH. Output is a risk ASSESSMENT, never a fraud verdict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SUSPICIOUS_TLDS = {"co", "info", "xyz", "top", "click", "link", "pw", "cc", "gq", "tk"}
SHORTENERS = ("bit.ly", "t.co", "goo.gl", "tinyurl.com", "cutt.ly", "is.gd")

_RULES: list[tuple[str, str, float, re.Pattern[str]]] = [
    ("urgency", "Urgency pressure (immediate action / deadline threats)", 0.22,
     re.compile(r"\b(urgent(?:ly)?|immediately|within \d+ (hours?|hrs?)|today|last chance|"
                r"act now|asap|expire[sd]? (?:in|today))\b", re.I)),
    ("account_threat", "Account suspension / freeze threat", 0.22,
     re.compile(r"\b(account|card|login|access)\b[^\.\n]{0,60}\b(suspend(?:ed|ing|s)?|"
                r"block(?:ed)?|freez(?:e|ed)|clos(?:e|ed|ing)|disabled|unavailable)\b", re.I)),
    ("payment_request", "Direct payment / transfer request", 0.2,
     re.compile(r"\b(transfer|wire|upi|immediate payment|pay (?:now|immediately|today)|"
                r"send (?:me )?(?:a )?(payment|funds|money|transfer)|net amount|"
                r"bank transfer)\b", re.I)),
    ("credential_request", "Requests credentials / sensitive data", 0.25,
     re.compile(r"\b(password|passcode|otp|one[- ]time (?:password|code)|cvv|"
                r"credit card number|pin code?|bank details?|account number|credentials|"
                r"login details?)\b", re.I)),
    ("secrecy", "Asks user to keep it secret / not verify", 0.2,
     re.compile(r"\b(do not (?:tell|inform|share|disclose|mention)|keep (?:this )?secret|"
                r"do not verify|do not contact|for your eyes only|confidential)\b", re.I)),
    ("impersonation", "Impersonation / authority language", 0.2,
     re.compile(r"\b(on behalf of|our (?:ceo|ct|manager|boss)|official (?:team|bank|help desk)|"
                r"it'?s me,|your (?:manager|boss|director)|senior (?:officer|executive))\b", re.I)),
    ("phone_verification", "Requests phone verification of sensitive info", 0.15,
     re.compile(r"(call|ring|contact)\s*(?:us|me|him|them)?\s*\+?[\d\s\-]{7,14}\b", re.I)),
]

_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+", re.I)


@dataclass
class Signal:
    id: str
    label: str
    weight: float
    evidence: str


def _snippet(text: str, start: int, end: int) -> str:
    a = max(0, start - 25)
    b = min(len(text), end + 25)
    s = text[a:b].replace("\n", " ")
    return ("…" if a > 0 else "") + s.strip() + ("…" if b < len(text) else "")


def run_rules(text: str) -> tuple[list[Signal], float]:
    signals: list[Signal] = []
    for sid, label, weight, pat in _RULES:
        m = pat.search(text)
        if m:
            signals.append(Signal(sid, label, weight, _snippet(text, m.start(), m.end())))

    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:")
        risky_reasons = []
        if not url.lower().startswith("https"):
            risky_reasons.append("plain http")
        host = re.sub(r"^https?://", "", url, flags=re.I).split("/")[0].split(":")[0].lower()
        tld = host.rsplit(".", 1)[-1]
        if tld in SUSPICIOUS_TLDS:
            risky_reasons.append(f"suspicious TLD '.{tld}'")
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            risky_reasons.append("IP address host")
        if any(s in host for s in SHORTENERS):
            risky_reasons.append("URL shortener")
        if risky_reasons:
            signals.append(Signal(
                "suspicious_link", "Suspicious link: " + "; ".join(risky_reasons),
                0.28, _snippet(text, m.start(), m.end())))
            break
    score = min(1.0, sum(s.weight for s in signals))
    return signals, round(score, 3)
