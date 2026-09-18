"""Fused multi-signal risk assessment.

score = 0.55 * rules_score + 0.45 * P(scam | text)
level = HIGH if score >= 0.65, MEDIUM if >= 0.35, else LOW

The blended score is decision support. The report always carries:
  - the signals that fired, each with an evidence snippet
  - model provenance (which components contributed)
  - a mandatory disclaimer that this is NOT a fraud determination
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .classifier import ScamClassifier
from .rules import run_rules

_clf = ScamClassifier()


@dataclass
class RiskReport:
    risk_level: str                 # LOW | MEDIUM | HIGH
    score: float
    signals: list[dict] = field(default_factory=list)
    components: dict = field(default_factory=dict)
    disclaimer: str = ("This is a risk assessment, not a definitive fraud "
                       "determination. Verify independently before acting on "
                       "any payment or credential request.")


def _level(score: float) -> str:
    return "HIGH" if score >= 0.65 else "MEDIUM" if score >= 0.35 else "LOW"


def assess_message(text: str, sender: str | None = None,
                   claimed_brand: str | None = None) -> RiskReport:
    text = (text or "").strip()
    if not text:
        return RiskReport("LOW", 0.0, [], {"rules": 0.0, "classifier": 0.0})
    signals, rules_score = run_rules(text)
    nb = _clf.probability(text)
    score = round(0.55 * rules_score + 0.45 * nb, 3)
    sig_dicts = [{"id": s.id, "label": s.label, "weight": s.weight,
                  "evidence": s.evidence} for s in signals]
    if nb >= 0.6:
        sig_dicts.append({"id": "language_model",
                          "label": f"Message language matches scam patterns (P={nb})",
                          "weight": round(0.45 * nb, 3),
                          "evidence": "Naive Bayes classifier on synthetic labeled corpus"})
    return RiskReport(
        risk_level=_level(score),
        score=score,
        signals=sig_dicts,
        components={"rules": rules_score, "classifier": nb,
                    "fusion": "0.55*rules + 0.45*classifier"},
    )
