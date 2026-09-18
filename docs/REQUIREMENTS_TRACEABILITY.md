# NEXUS — Requirements Traceability Matrix

Every acceptance criterion mapped to its implementation, API surface,
frontend screen and test evidence. Verification status reflects what was
actually run in this audit (see `docs/REPOSITORY_AUDIT.md` and
`docs/FINAL_AUDIT.md`), not what the code merely claims to do.

| # | Requirement | Implementation | API | Frontend | Test evidence | Status |
|---|---|---|---|---|---|---|
| 1 | Register/login | `api/auth.py` (`register`, `login`) | `POST /auth/register`, `POST /auth/login` | `LandingPage.tsx` | `test_api_core.py::test_register_login_me` | VERIFIED |
| 2 | User authentication | `api/deps.py::get_current_user`, `core/security.py` (JWT HS256) | `Authorization: Bearer` on all protected routes | `lib/api.ts` (token storage), `Layout.tsx` (`/auth/me` on load) | Same as #1; 401 path tested implicitly by isolation tests | VERIFIED |
| 3 | User authorization | Every route's DB query filters by `user.id`; ownership checks 404 on mismatch (`documents.py:58,81`, `approvals.py:18-24`, `agents.py:85-86`) | all `/api/v1/*` routes except `/auth/register`, `/auth/login`, `/health`, `/ready` | — | `test_api_core.py::test_user_isolation`, `test_agents.py::test_isolation_of_agent_runs` | VERIFIED |
| 4 | Document upload | `api/documents.py::upload`, `services/storage.py` (extension allowlist, magic-byte check, size cap, filename sanitisation) | `POST /documents/upload` (202) | `DocumentsPage.tsx` | `test_api_core.py`, `tests/test_e2e.py` | VERIFIED |
| 5 | Document processing | `services/ingest.py::run_ingestion` (background job) | `GET /documents/{id}` (status polling) | `DocumentsPage.tsx` (polls while UPLOADED/PROCESSING/INDEXING) | `tests/test_e2e.py::test_full_loop` | VERIFIED |
| 6 | Document classification | `ml/extraction/classify.py` (weighted-keyword, 13 categories) | surfaced via `Document.doc_type`/`doc_type_confidence` | `DocumentsPage.tsx` | `test_ml_units.py` | VERIFIED |
| 7 | Entity extraction | `ml/extraction/entities.py` (EMAIL/PHONE/URL/DOMAIN/MERCHANT/PERSON/ACCOUNT_REF, per-kind confidence) | via document detail | `DocumentsPage.tsx` | `test_ml_units.py` | VERIFIED |
| 8 | Chunking | `services/chunking.py` (paragraph/page-aware, ~700 char, 120 overlap) | internal to ingestion | — | exercised by `tests/test_e2e.py` (search/ask depend on it) | VERIFIED |
| 9 | Embeddings | `ml/embeddings/hasher.py` (deterministic local hashing-trick, 384-d); `llm/factory.py` swaps in OpenAI embeddings when configured+keyed | — | — | `test_ml_units.py`; end-to-end via `test_full_loop` | VERIFIED |
| 10 | Search | `rag/retriever.py::HybridRetriever` (vector + BM25, user-scoped) | `POST /search` | `RagEvalPage.tsx` | `test_full_loop` | VERIFIED |
| 11 | RAG | `rag/context.py`, `rag/answers.py` | `POST /ask` | `RagEvalPage.tsx` | `test_full_loop` (grounded answer assertion) | VERIFIED |
| 12 | Source-grounded answers | `rag/answers.py` (`grounded` flag, refusal when no evidence) | `POST /ask` (`grounded`, `confidence`) | `RagEvalPage.tsx` | `test_full_loop`; `test_ask_refuses_when_not_found` | VERIFIED |
| 13 | Citations | `rag/answers.py::_sources()` (validates against actually-retrieved refs) | `AskOut.sources` | `RagEvalPage.tsx` | `test_full_loop` (`sources[0].document_name`) | VERIFIED |
| 14 | RAG evaluation | `ml/evaluation/{metrics,runner,dataset}.py`, `services/evaluation_service.py` against `data/demo/eval_set.json` (12 cases) | `GET /analytics/rag-quality`, `POST /analytics/rag-quality/run` | `RagEvalPage.tsx` (explicit "Not yet evaluated" empty state) | `test_full_loop` (asserts real precision/recall/citation/correctness values); **no dedicated unit test of `evaluation_service.py` itself** | PARTIAL (works, coverage gap noted) |
| 15 | Transaction ingestion | `services/transactions.py::import_transactions`, CSV parsing | `POST /documents/upload` (CSV path) | `DocumentsPage.tsx` | `test_full_loop`, `test_data_science.py` | VERIFIED |
| 16 | Transaction analysis | `api/analytics.py` (`/overview`, `/spending`) | `GET /analytics/overview`, `/spending` | `DataLabPage.tsx` | `test_full_loop` | VERIFIED |
| 17 | Recurring-payment detection | `ml/recurring/detector.py` (real interval/amount-CV confidence formula) | `GET /insights/subscriptions` | `DataLabPage.tsx` | `test_ml_units.py`, `test_full_loop` (Cloudvault price-increase assertion) | VERIFIED |
| 18 | Anomaly detection | `ml/anomaly/{features,model}.py` (IsolationForest + robust-z fallback) | `GET /insights/anomalies` | `DataLabPage.tsx` | `test_ml_units.py` | VERIFIED |
| 19 | Risk analysis | `ml/risk/{classifier,rules,report}.py` (NB + heuristic fusion) | `POST /risk/analyze`, `GET /analytics/risk` | `RiskCenterPage.tsx` | `test_ml_units.py`, `test_full_loop` (HIGH on suspicious message) | VERIFIED |
| 20 | Deadline extraction | `services/records.py::derive_deadlines` (regex/date parsing) | `GET /insights/deadlines` | `DashboardPage.tsx` | `test_full_loop` | VERIFIED |
| 21 | Forecasting | `ml/forecasting/model.py` (`MIN_MONTHS=6`, explicit insufficient-data response) | `GET /insights/forecast` | `DataLabPage.tsx` | `test_data_science.py::test_forecast_insufficient_data`, `test_ml_units.py` | VERIFIED |
| 22 | Knowledge graph | `services/graph.py` (relational entities/relationships) | `GET /insights/graph` | `KnowledgeGraphPage.tsx` (client-side force layout) | `test_full_loop` (node/edge count assertions); `test_concurrency.py` (no duplicate nodes under concurrent ingestion) | VERIFIED |
| 23 | Agent planner | `agents/planner.py` | `POST /agent/run` (SSE) | `CommandCenterPage.tsx` | `test_agents.py`, `test_full_loop` | VERIFIED |
| 24 | Agent tools | `agents/tools.py` (fixed registry, typed args, per-tool risk class) | via `/agent/run` | `CommandCenterPage.tsx`, `AgentTracePage.tsx` | `test_agents.py` | VERIFIED |
| 25 | Safe tool execution | `agents/executor.py` (SAFE tools auto-execute; no eval/exec/raw-SQL surface, grep-verified) | — | — | `test_agents.py` | VERIFIED |
| 26 | Consequential-action approval | `agents/executor.py:150-181` (gate → `Approval` row persisted → run paused) | `POST /agent/run` pauses with `WAITING_APPROVAL` | `ApprovalsPage.tsx` | `test_agents.py::test_agent_weekly_attention_stops_for_approval`, `test_full_loop` | VERIFIED |
| 27 | Approval rejection | `api/approvals.py::reject` → `executor.py:272-276` (STEP_SKIPPED, tool `.fn` never called) | `POST /approvals/{id}/reject` | `ApprovalsPage.tsx` | `test_agents.py` | VERIFIED |
| 28 | Approval execution | `api/approvals.py::approve` → `resume_after_approval` | `POST /approvals/{id}/approve` | `ApprovalsPage.tsx` (awaits real result) | `test_agents.py` | VERIFIED |
| 29 | Agent trace | `db/models.py::AgentStep` (persisted, real args/result/duration/status) | `GET /agent/tasks`, `/agent/tasks/{id}` | `AgentTracePage.tsx` (renders persisted steps, no fake "thinking" animation) | `test_agents.py` | VERIFIED |
| 30 | Audit trail | `audit/service.py` (append-only `AuditEvent`) | surfaced via `/analytics/overview` (`audit_events` count) | — | `test_full_loop` (`ov["audit_events"] > 0`) | VERIFIED |
| 31 | Notifications | `services/notify.py`, `db/models.py::Notification`, `schemas/__init__.py::NotificationOut` | `GET /notifications`, `POST /{id}/read`, `/read-all` | `components/Layout.tsx::NotificationBell` (header dropdown, unread badge, mark-read/mark-all-read) | `test_notifications_list_and_mark_read`; live-verified in a browser (Playwright) against the seeded demo account — real unread badge, real notification content, mark-all-read confirmed | VERIFIED (endpoint was completely broken — `NotificationOut` couldn't validate ORM rows, 500 on any non-empty list, zero prior test coverage — found via live browser testing and fixed in this audit; see REPOSITORY_AUDIT.md) |
| 32 | Dashboard | `DashboardPage.tsx` | `GET /insights/overview`, `/deadlines`, `/subscriptions` | `DashboardPage.tsx` | frontend audit: real loading/error/empty states, no hardcoded numbers | VERIFIED |
| 33 | Real-data charts | Recharts fed entirely from fetched data (`DataLabPage.tsx`) | multiple | `DataLabPage.tsx` | frontend audit: no embedded static arrays found | VERIFIED |
| 34 | Data Science Lab | `DataLabPage.tsx` (4 tabs: subscriptions/anomalies/forecast/spending) | `/insights/subscriptions`, `/anomalies`, `/forecast`, `/analytics/spending` | `DataLabPage.tsx` | frontend audit | VERIFIED |
| 35 | Privacy page | `api/auth.py::delete_me` (password-confirmed account deletion, cascades, audit-logged) | `DELETE /auth/me` | `apps/web/src/pages/PrivacyPage.tsx` — real per-category data counts from `/analytics/overview`, password + type-DELETE-to-confirm double gate, linked from the sidebar | Live-verified end-to-end in a browser: registered a disposable account, deleted it via the UI, confirmed the redirect to `/login`, confirmed the same credentials now fail login (`bad_credentials`), confirmed the `account.deleted` audit row persisted in the database | VERIFIED |
| 36 | Demo dataset | `scripts/generate_demo_data.py`, `data/demo/` (committed synthetic) | `make demo` | — | `tests/test_e2e.py` runs directly against it | VERIFIED |
| 37 | Tests | `apps/api/tests/*.py`, `tests/test_e2e.py` | — | — | 36/36 passing after this audit's fixes (was 35, +1 new regression test) | VERIFIED |
| 38 | Frontend build | `apps/web` | — | `npm run build` | executed in this workspace: succeeds | VERIFIED |
| 39 | Typecheck | `tsconfig*.json` (strict) | — | `npm run typecheck` | executed in this workspace: 0 errors | VERIFIED |
| 40 | Lint | `pyproject.toml` (`ruff`) | — | — | `ruff check .`: 0 issues (1 fixed in this audit); no frontend lint script configured (eslint not set up) | PARTIAL (backend clean; frontend has no lint script) |
| 41 | Docker where available | `infrastructure/docker/Dockerfile.{api,web}`, `docker-compose.yml` | — | — | Docker not available in this verification environment; reviewed statically only | NOT VERIFIED |
| 42 | Cloud infrastructure definitions | `infrastructure/aws/terraform/main.tf` | — | — | Static review only (no hardcoded secrets found); not planned/applied | NOT VERIFIED (definitions exist; no deployment claimed) |
| 43 | Documentation | `README.md`, `docs/*.md` | — | — | Cross-checked against code in this audit; updated where stale (security.md, README verification numbers) | VERIFIED |
| 44 | Security | see `docs/security.md`, `docs/threat-model.md`, `docs/REPOSITORY_AUDIT.md` | — | — | Findings fixed and re-tested in this audit | VERIFIED (with documented residual risks) |
| 45 | User data deletion | `api/auth.py::delete_me` (`wipe_user_memory`, cascade delete, audit log survives as a dangling but harmless reference) | `DELETE /auth/me` | `apps/web/src/pages/PrivacyPage.tsx` (same feature as #35) | Same live end-to-end verification as #35 | VERIFIED |

## Gaps closed in this pass

- **#31 Notifications / #35 Privacy page / #45 deletion UI** were
  initially flagged PARTIAL (real backends, no located frontend). Rather
  than leave that as a permanent gap, this audit built the three missing
  frontend surfaces (`PrivacyPage.tsx`, `NotFoundPage.tsx`, a notification
  bell in `Layout.tsx`) against the existing design system and verified
  them live in a browser end-to-end — which is also how the
  `NotificationOut` schema bug (a completely broken, zero-coverage
  endpoint) was caught. See `docs/REPOSITORY_AUDIT.md` for both.

## Remaining gaps (not fixed in this pass — reason given)

- **#14 RAG evaluation service**: the aggregation math (`compute_metrics`)
  is unit-tested; the service that wires it to the live retriever/LLM
  (`evaluation_service.py`) is only exercised indirectly through the E2E
  test. A dedicated test would catch a regression here faster.
- **#40 Frontend lint**: no ESLint config exists in `apps/web`; `tsc
  --noEmit` catches type errors but not style/correctness lint rules a
  linter would.
- **#41/#42**: infrastructure-as-code exists and was read for obvious
  misconfiguration, but "the Terraform compiles and contains no
  hardcoded secrets" is not the same claim as "this runs in AWS" — the
  matrix marks these NOT VERIFIED rather than implying deployment.
