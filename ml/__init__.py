"""NEXUS ML package.

Pure data-science modules with no framework dependencies:
  - ml.extraction    date / amount / entity extraction, document classification
  - ml.embeddings    deterministic local embedding (offline mock mode)
  - ml.recurring     recurring-payment / subscription detection
  - ml.anomaly       transaction anomaly detection (IsolationForest / robust-z)
  - ml.forecasting   monthly spending forecast with explicit insufficient-data
  - ml.risk          multi-signal scam/risk engine (rules + Naive Bayes)
  - ml.evaluation    RAG evaluation dataset + metrics + runner

Every module documents its purpose, features, metrics and limitations.
No module fabricates outputs: insufficient input produces an explicit
insufficient-data result, never a made-up number.
"""

__version__ = "0.1.0"
