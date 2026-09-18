# NEXUS — Data Science Notes

Purpose, features, metrics and **limitations** for every model. All models
live in the framework-free `ml/` package and are unit-tested.

## 1. Transaction anomaly detection — `ml/anomaly`

**Problem**: flag transactions that deviate from the user's *own* history.
Interpretation contract: **anomaly ≠ fraud**. UI copy is always
"Unusual transaction — review recommended".

**Features** (per transaction):

| feature | why |
|---|---|
| `amount`, `log_amount` | scale + heavy tail |
| `hour`, `weekday`, `day_of_month`, `month` | temporal habits |
| `merchant_freq` | how often this merchant appears |
| `new_merchant` | first appearance |
| `merchant_z` | robust (median/MAD) z-score vs that merchant's own history |

**Model**: scikit-learn `IsolationForest(n_estimators=200, contamination=0.05,
random_state=42)`. Fallback: robust per-feature z-scores if sklearn is absent
(keeps the module runnable in minimal environments).

**Labels**: raw anomaly scores are self-calibrated on the fitted set:
`UNUSUAL ≥ p95`, `HIGHLY_UNUSUAL ≥ p99`. This is an honest self-calibration,
not a fraud model. Explanations cite the top-3 contributing features with
observed value and clipped z-score.

**Requirements**: ≥ 8 transactions, else an explicit
"Not enough transaction history" result (no invented alerts).

**Known limitations**: one-off legitimate large expenses (flights, repairs)
do flag as UNUSUAL — that is the feature working, and the explanations say
why (new merchant + high amount). No drift retraining yet.

## 2. Recurring / subscription detection — `ml/recurring`

**Method**
1. Normalise merchant from description (strip digits + generic tokens).
2. Group by merchant; require **≥ 3 occurrences**.
3. Classify median interval: WEEKLY ~7d (±4), MONTHLY ~30d (±6),
   QUARTERLY ~90d (±14), YEARLY ~365d (±25).
4. Regularity = stdev(intervals)/median; amount stability = CV of last 3.
5. Confidence = 0.4 + 0.06·occurrences, penalised for irregularity / CV,
   capped at 0.95.

**Outputs**: frequency, next due (last + median interval), monthly
equivalent, annualised cost, **price increase** (last amount > 1.05 ×
median of earlier amounts → from/to/pct/date), LAPSED status when no
payment for >2.5 intervals.

**Honesty rule**: LAPSED is a *factual payment-observation* note
("no payment observed for >2.5 cycles — verify whether still wanted").
NEXUS never claims a subscription is "unused" — it has no usage signal.

## 3. Forecasting — `ml/forecasting`

**Mandatory behaviour**: < 6 active months of history →
`ok=False` + "Not enough historical data to produce a reliable forecast
(need >= 6 months with activity)". NEXUS never invents a forecast.

**Model** (when enough data): monthly totals (up to 24 months) →
3-month moving average → least-squares linear trend → seasonal adjustment
= mean residual per calendar month. Forecast = trend(month) +
seasonal(month); interval = ±1.96·σ(residuals).

**Limitations (stated in the API response)**: 6–24 months is a small
sample; intervals are wide; one-off expenses distort the series; this is
decision support, not a point prediction.

## 4. Scam risk engine — `ml/risk`

**Fusion**: `score = 0.55·rules + 0.45·P(scam|text)`; levels
HIGH ≥ 0.65, MEDIUM ≥ 0.35, else LOW. Output is always a risk
**assessment with a disclaimer**, never "fraud".

**Rules** (named heuristics, hand-set weights, each with an evidence snippet):
urgency pressure, account-suspension threat, payment/transfer request,
credential request, secrecy demand, impersonation/authority, phone
verification demand, suspicious link (http-only, risky TLDs, IP host,
shorteners).

**Classifier**: Multinomial Naive Bayes (Laplace α=0.1), pure Python,
trained on ~90 **synthetic, versioned, explicitly-labeled** messages in
`ml/risk/classifier.py`. Held-out metrics (fixed 80/20 split, seed 42) are
computed at runtime via `ScamClassifier.holdout_metrics()` — never
hardcoded in UI copy.

**Limitations**: synthetic training data, narrow phrase coverage, English-
centric; designed as a first-pass triage layer, not a detection guarantee.

## 5. Evaluation — `ml/evaluation`

- **RAG**: 12 curated cases (question, expected document, expected
  keywords) in `data/demo/eval_set.json`. Metrics: retrieval
  precision@1, recall@5, citation accuracy, answer correctness, latency.
  Runs are stored per-case (`rag_eval_results`) and surfaced in the RAG &
  Eval page. Before any run, the API reports **"Not yet evaluated"** —
  no placeholder numbers.
- **Risk**: hold-out accuracy/recall/precision computed at runtime.
- **Anomaly/forecast/recurring**: unit-tested with seeded synthetic data;
  results carry model name + n_scored in `model_predictions`.

**Metric honesty policy**: any metric shown in the UI is computed from an
actual run against the actual current data. If there is no run, the UI
says so.

## 6. Extraction & classification — `ml/extraction`

- **Dates**: 5 explicit formats (14 March 2027, March 14 2027, 2027-03-14,
  14/03/2027, 14-03-27), day-first default for numeric dates (IN),
  2-digit year expansion, invalid dates dropped (never guessed).
- **Amounts**: currency-marker before/after (₹/Rs/INR/$/€/£), Indian
  grouping (12,50,000) and Western grouping handled.
- **Entities**: EMAIL, PHONE, URL (with suspicious-TLD/shortener/IP flags),
  DOMAIN, MERCHANT, PERSON, ACCOUNT_REF — each with confidence + evidence
  snippet.
- **Classification**: weighted keyword scoring across 13 categories,
  confidence = top/(top+second). Fast, explainable, honest; an LLM can
  override when configured.
