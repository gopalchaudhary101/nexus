"""Rule-based document classification.

Method
    Weighted keyword scoring per category, normalised to [0, 1] against the
    strongest category. Used as a fast, explainable classifier; the LLM layer
    may override it when a provider is configured (see apps/api/app/rag).

Confidence = top_score / (top_score + second_score) when both are non-zero,
which keeps confident single-category docs near 1.0 and ambiguous ones lower.
"""
from __future__ import annotations

import re

CATEGORIES = [
    "BILL", "BANK_STATEMENT", "INVOICE", "RECEIPT", "INSURANCE", "CONTRACT",
    "WARRANTY", "SUBSCRIPTION", "TRAVEL", "EDUCATION", "EMPLOYMENT", "IDENTITY", "OTHER",
]

_WEIGHTS: dict[str, list[tuple[str, float]]] = {
    "INSURANCE": [("insurance", 3), ("policy", 3), ("premium", 2.5), ("claim", 2), ("coverage", 2.5),
                  ("insured", 2.5), ("sum assured", 2), ("renewal", 1.5), ("exclusion", 1.5)],
    "BANK_STATEMENT": [("bank statement", 4), ("account statement", 4), ("available balance", 3),
                       ("closing balance", 3), ("txn", 2), ("withdrawn", 2), ("credited", 2),
                       ("upi", 1.5), ("ifsc", 2.5)],
    "SUBSCRIPTION": [("subscription", 3.5), ("auto-renew", 3), ("auto renew", 3), ("monthly plan", 2.5),
                     ("recurring", 2), ("membership", 2), ("plan", 1), ("cancellation", 1.5)],
    "BILL": [("bill", 2.5), ("due date", 3), ("amount due", 3), ("electricity", 2.5), ("water", 1.5),
             ("billing period", 2.5), ("consumer number", 3), ("meter", 1.5), ("pay by", 2)],
    "INVOICE": [("invoice", 3.5), ("tax invoice", 4), ("gstin", 4), ("payment terms", 2),
                ("billing to", 2), ("taxable value", 2.5), ("igst", 2), ("cgst", 2)],
    "RECEIPT": [("receipt", 3.5), ("cash", 1.5), ("till", 2.5), ("thank you for your purchase", 3),
                ("mode of payment", 2), ("gst invoice no", 1.5), ("voucher", 2)],
    "CONTRACT": [("agreement", 3), ("contract", 3), ("parties", 2), ("lease", 3), ("landlord", 3.5),
                 ("tenant", 3.5), ("term of this", 2.5), ("cancellation", 1.5), ("notice", 1.5),
                 ("confidentiality", 2), ("whereas", 2)],
    "WARRANTY": [("warranty", 4), ("guarantee", 3), ("defect", 2), ("manufacturer", 2),
                 ("repair", 1.5), ("coverage period", 2), ("serial number", 2)],
    "TRAVEL": [("flight", 3), ("booking", 2), ("ticket", 2.5), ("hotel", 2.5), ("itinerary", 3),
               ("pnr", 3.5), ("boarding", 2), ("cabin", 2), ("departure", 1.5)],
    "EDUCATION": [("university", 3), ("college", 3), ("degree", 2.5), ("certificate", 2),
                  ("semester", 2.5), ("transcript", 3), ("course", 1.5), ("examination", 2)],
    "EMPLOYMENT": [("offer letter", 4), ("employment", 3), ("designation", 3), ("joining", 2),
                   ("ctc", 3.5), ("payroll", 2.5), ("probation", 3), ("employer", 2)],
    "IDENTITY": [("aadhaar", 4), ("passport", 4), ("voter", 3.5), ("driving license", 3.5),
                 ("national id", 3.5), ("identity card", 3)],
}


def classify_document(text: str) -> tuple[str, float, dict[str, float]]:
    low = (text or "").lower()
    scores: dict[str, float] = {}
    for cat, terms in _WEIGHTS.items():
        s = 0.0
        for term, w in terms:
            s += w * len(re.findall(re.escape(term), low))
        scores[cat] = s
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_score = ranked[0]
    second_score = ranked[1][1]
    if top_score <= 0:
        return "OTHER", 0.3, scores
    confidence = top_score / (top_score + second_score) if (top_score + second_score) > 0 else 0.5
    confidence = round(max(0.3, min(0.99, confidence)), 3)
    return top, confidence, scores
