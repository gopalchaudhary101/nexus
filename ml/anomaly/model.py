"""Transaction anomaly detection.

Model
    Primary:   scikit-learn IsolationForest (n_estimators=200, contamination=0.05)
    Fallback:  robust per-feature z-scores (median/MAD) if sklearn is missing.
    (The fallback keeps the module usable in minimal environments.)

Labels
    Scores are normalised to [0, 1]. Thresholds are calibrated on the fitted
    set itself: UNUSUAL >= 95th pct, HIGHLY_UNUSUAL >= 99th pct. This is an
    honest self-calibration, NOT a claim of fraud detection.

Interpretation (mandatory, per product spec)
    Anomaly != fraud. Output is phrased "Unusual transaction — review
    recommended." Explanations cite the top contributing features with
    their observed values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

import numpy as np

from .features import build_features


@dataclass
class AnomalyResult:
    index: int
    label: str                    # NORMAL | UNUSUAL | HIGHLY_UNUSUAL
    score: float                  # 0..1
    explanations: list[dict] = field(default_factory=list)  # feature/value/why
    model: str = "isolation-forest-v1"


class TransactionAnomalyDetector:
    def __init__(self) -> None:
        self._model: object | None = None
        self._feature_names: list[str] = []
        self._medians: np.ndarray | None = None
        self._mads: np.ndarray | None = None
        self._unusual_q: float = 0.95
        self._high_q: float = 0.99
        self.fitted = False

    def fit(self, transactions: list[dict]) -> TransactionAnomalyDetector:
        if len(transactions) < 8:
            raise ValueError("Need at least 8 transactions to fit; got "
                             f"{len(transactions)}. Insufficient data.")
        feats, names = build_features(transactions)
        self._feature_names = names
        X = np.array([[f[n] for n in names] for f in feats], dtype=np.float64)
        self._medians = np.median(X, axis=0)
        mads = np.array([
            median(np.abs(X[:, i] - self._medians[i])) or 1e-6 for i in range(X.shape[1])
        ])
        self._mads = 1.4826 * mads
        try:
            from sklearn.ensemble import IsolationForest
            self._model = IsolationForest(
                n_estimators=200, contamination=0.05, random_state=42, n_jobs=2
            ).fit(X)
            self._raw_scores = -self._model.score_samples(X)  # type: ignore[union-attr]
            self.model_name = "isolation-forest-v1"
        except ImportError:  # pragma: no cover - sklearn absent
            self._model = None
            self._raw_scores = self._robust_scores(X)
            self.model_name = "robust-z-v1"
        qs = np.quantile(self._raw_scores, [self._unusual_q, self._high_q])
        self._t_unusual, self._t_high = float(qs[0]), float(qs[1])
        lo, hi = float(self._raw_scores.min()), float(self._raw_scores.max())
        self._lo, self._hi = lo, hi
        self.fitted = True
        return self

    def _robust_scores(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self._medians) / self._mads
        return np.abs(Z).max(axis=1)

    def _explain(self, feat_row: dict, names: list[str]) -> list[dict]:
        assert self._medians is not None and self._mads is not None
        z = {n: (feat_row[n] - self._medians[i]) / self._mads[i]
             for i, n in enumerate(names)}
        ranked = sorted(z.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
        human = {
            "merchant_z": "amount far above this merchant's historical average",
            "amount": "amount far above the typical transaction amount",
            "log_amount": "amount far above the typical transaction amount",
            "new_merchant": "first-time merchant in your history",
            "hour": "unusual time of day for your transactions",
            "merchant_freq": "merchant you rarely deal with",
            "weekday": "unusual day of week",
            "day_of_month": "unusual day of month",
            "month": "unusual month",
        }
        return [{"feature": n, "value": round(feat_row[n], 3),
                 "z": round(max(min(z[n], 20.0), -20.0), 2),
                 "why": human.get(n, "deviates from your typical pattern")} for n, _ in ranked]

    def predict(self, transactions: list[dict]) -> list[AnomalyResult]:
        if not self.fitted:
            raise RuntimeError("Detector not fitted. Call fit() first.")
        assert self._medians is not None and self._mads is not None
        feats, names = build_features(transactions)
        X = np.array([[f[n] for n in names] for f in feats], dtype=np.float64)
        raw = (-self._model.score_samples(X) if self._model is not None  # type: ignore[attr-defined]
               else self._robust_scores(X))
        lo, hi = min(self._lo, float(raw.min())), max(self._hi, float(raw.max()))
        norm = (raw - lo) / (hi - lo) if hi > lo else np.zeros_like(raw)
        norm = np.clip(norm, 0.0, 1.0)
        out: list[AnomalyResult] = []
        for i, row in enumerate(feats):
            s = float(norm[i])
            label = ("HIGHLY_UNUSUAL" if s >= self._t_high else
                     "UNUSUAL" if s >= self._t_unusual else "NORMAL")
            out.append(AnomalyResult(index=i, label=label, score=round(s, 3),
                                     explanations=self._explain(row, names)
                                     if label != "NORMAL" else [], model=self.model_name))
        return out

    @property
    def model_name(self) -> str:
        return getattr(self, "_model_name", "isolation-forest-v1")

    @model_name.setter
    def model_name(self, v: str) -> None:
        self._model_name = v
