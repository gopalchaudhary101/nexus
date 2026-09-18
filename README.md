# NEXUS — Personal Life Intelligence & Action OS

> An AI operating layer for your personal digital life. NEXUS turns scattered
> documents, bills, subscriptions, transactions and messages into a **personal
> knowledge graph**, answers questions **with source citations**, runs real
> **data science** (anomaly detection, subscription intelligence, forecasting),
> scores **message risk**, and executes **safe agentic workflows** with
> human-in-the-loop approvals and a full audit trail.

Design principle: **observe → understand → retrieve evidence → analyze →
predict → explain → propose → ask permission → act safely.**

---

## What actually works (honest capability map)

| capability | status |
|---|---|
| Document ingestion (PDF/DOCX/TXT/MD/CSV, images w/ OCR when installed) | ✅ real pipeline: validation → storage → extraction → classification → chunking → embedding → entities → deadlines → knowledge graph |
| Hybrid search (vector + BM25) with per-user isolation | ✅ |
| Grounded Q&A with page citations + confidence + refusal-when-no-evidence | ✅ (extractive in mock mode; LLM mode via env-configured provider) |
| Subscription intelligence (frequency, next due, annual cost, **price increases**, lapsed — never "unused" claims) | ✅ |
| Transaction anomaly detection (IsolationForest, self-calibrated thresholds, feature-level explanations, "anomaly ≠ fraud" framing) | ✅ |
| Spending forecast (trend + seasonal, 95% bands, explicit *insufficient-data* response below 6 months) | ✅ |
| Scam risk engine (named heuristics + Naive Bayes on synthetic labeled corpus, runtime-computed holdout metrics, disclaimers, never "fraud") | ✅ |
| Agentic workflows (declared tool plan, SAFE/SENSITIVE/CONSEQUENTIAL policy, approval gates, SSE-traced execution, audit trail, memory) | ✅ |
| RAG evaluation (12 curated cases, live-computed precision@1/recall@5/citation/answer metrics, "Not yet evaluated" until run) | ✅ |
| LLM text generation | 🔌 **mock mode by default** (declared deterministic mode); OpenAI/Anthropic/Gemini activate via env credentials — never silent |
| `send_email` / `cancel_subscription` | 🔌 **integration stubs**: approved execution returns an explicit `SIMULATED` result with the reason; nothing is ever faked |
| Cloud (AWS) | 📦 Terraform + Dockerfiles written (VPC/ECS-Fargate/RDS-pgvector/S3/SQS/Secrets/CloudWatch); local dev needs no cloud |

No fake numbers anywhere: every metric in the UI is computed from an actual
run against the current data — or the UI says "Not yet evaluated".

## Quickstart (5 minutes)

Prereqs: Python 3.11+, Node 20+. No Docker or cloud required.

```bash
# 1. backend deps
make install

# 2. synthetic demo dataset + demo user (no real personal data)
make demo
#    → login: demo@nexus.dev / nexus-demo-2026

# 3. API (port 8000)
uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000

# 4. web (port 5173, proxies /api)
make web-install
cd apps/web && npm run dev
```

Open http://localhost:5173 and sign in with the demo credentials.

### Try the 8 demo scenarios

1. **Dashboard** — see "needs attention": insurance renewal in 8 days,
   electricity bill due in 10 days, streaming renewal in 15 days, a HIGH
   risk message and flagged unusual transactions — all derived from data.
2. **Ask** (RAG & Eval page) — *"When does my insurance policy expire?"*
   → grounded answer quoting `insurance_policy.pdf — Page 1` with
   confidence; ask about something not in your docs → explicit refusal,
   zero sources.
3. **Command Center** — *"What needs my attention this week?"* → live SSE
   trace: intent → tool calls (deadlines, retrieval, subscriptions,
   anomalies, report) → then **pauses for approval** to create a reminder.
4. **Approvals** — approve (or reject) the pending reminder; watch the run
   resume and complete in the **Agent Trace** with full step history.
5. **Data Lab** — subscriptions incl. **Cloudvault price +20%** and lapsed
   Music Hub (factual note, no usage claim); anomalies = the seeded
   transfers with feature-level explanations; forecast with 95% bands.
6. **Risk Center** — run the bundled suspicious messages (bank scare,
   CEO fraud) vs a normal notice; inspect signals + evidence + disclaimer.
7. **Knowledge Graph** — live force-directed view of your documents,
   merchants, people, deadlines and risks (relational storage).
8. **RAG & Eval** — press **Run evaluation**: 12 curated questions run
   against the live pipeline; real metrics appear (the seeded demo set
   scores P@1 1.0 / citations 1.0 — and will drop if you delete documents).

## Repository layout

```
apps/api/        FastAPI service (16-table schema, JWT auth, SSE agents)
apps/web/        React 18 + TS (strict) + Tailwind + TanStack Query + Recharts
ml/              framework-free data science (anomaly, recurring, forecast,
                 risk, extraction, embeddings, evaluation)
data/demo/       committed synthetic dataset (documents, transactions,
                 messages, eval ground truth) — no real PII
scripts/         generate_demo_data.py, seed_demo.py
tests/           end-to-end scenario test
docs/            architecture, data-science, rag, agents, security,
                 threat-model, deployment
infrastructure/  docker (API/web images) + aws/terraform
.github/         CI: ruff + mypy + pytest + frontend type-check/build
```

## Verification (executed in this workspace)

```bash
ruff check ml apps/api tests scripts            # All checks passed
mypy ml apps/api/app --ignore-missing-imports   # Success: 0 issues, 77 files
python3 -m pytest apps/api/tests tests          # 36 passed (API, DS, agents, e2e, concurrency)
pip-audit -r apps/api/requirements.txt          # No known vulnerabilities
cd apps/web && npm run typecheck && npm run build   # strict tsc + vite build OK
```

See `docs/FINAL_AUDIT.md` for the full production-readiness review (what was
verified, what was fixed, what remains a documented limitation) and
`docs/REQUIREMENTS_TRACEABILITY.md` for a criterion-by-criterion map to code
and tests.

The e2e test performs the full loop: register → upload the whole demo set →
wait for ingestion → grounded cited answer → subscription/price-increase
intelligence → risk engine → agent run with approval gate → live RAG
evaluation with metric assertions → knowledge graph → analytics.

## Architecture in one breath

Local default: **SQLite + hash embedder (384-d, deterministic) + mock LLM
(declared) + in-process job runner**. Production: **Postgres 16 + pgvector
(`NEXUS_USE_PGVECTOR=1`), OpenAI embeddings/LLM (credential-gated), S3,
SQS, AWS (CloudFront → ALB → ECS Fargate → RDS) via Terraform.** Every seam
is configuration, not code fork. See `docs/architecture.md`.

## Security posture (summary)

- PBKDF2-SHA256 (200k) passwords, 8h JWT, auth rate limiting
- Per-user isolation on every query (tested) — retrieval is tenant-scoped
- Upload validation: extension + magic bytes + size + filename sanitisation
- Prompt-injection defense: retrieved content is labelled untrusted data;
  answers grounded or refused; citations validated (tested)
- Agents: fixed tool registry (no shell/eval), risk-classed approvals
  (fail-closed default), simulated external actions labelled SIMULATED
- Append-only audit trail for every consequential event

Details: `docs/security.md`, `docs/threat-model.md`.

## Project philosophy (and what this is not)

- **No vibe coding**: every dashboard number is computed from your data at
  request time; there are no placeholder charts, fake analytics or fake
  agentic animations.
- **No hallucinated fields**: extracted values carry value + confidence +
  evidence; missing fields are simply absent.
- **No fraud labels, no usage claims, no invented forecasts**: the product
  surfaces deviations and probabilities with disclaimers, and says
  "Not enough data" when it cannot.
- **NEXUS is decision support**, not a legal, medical or financial advisor.

## Demo credentials

| field | value |
|---|---|
| email | `demo@nexus.dev` |
| password | `nexus-demo-2026` (override: `NEXUS_DEMO_PASSWORD` before `make seed`) |

The demo data is 100% synthetic (generated by `scripts/generate_demo_data.py`);
dates are anchored to the project timeframe so deadlines line up with the
dashboard.

## License

MIT — see [LICENSE](LICENSE).
