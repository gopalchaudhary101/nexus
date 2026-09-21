# NEXUS — Final Production-Readiness Audit

This is a closing summary of a full audit-and-fix pass over an inherited
NEXUS codebase. It complements, not replaces, `docs/REPOSITORY_AUDIT.md`
(the itemized findings table) and `docs/REQUIREMENTS_TRACEABILITY.md`
(criterion-by-criterion evidence). Every claim below was verified by
actually running something in this workspace — commands and outputs are
reproduced, not paraphrased from memory.

## Architecture (what actually exists)

A FastAPI + SQLAlchemy backend (`apps/api/app`) with a 20-table schema
(users, documents/chunks/entities, merchants/transactions/subscriptions,
deadlines, risks, agent runs/steps, approvals, audit events, model
predictions, RAG eval results, notifications, knowledge graph entities/
relationships, memory), a framework-free ML layer (`ml/`: recurring-
payment detection, anomaly detection, forecasting, a scam-risk NB
classifier + heuristic rules, document extraction, a local hashing-trick
embedder, RAG evaluation), a React 18 + TypeScript (strict) + TanStack
Query + Recharts frontend (`apps/web`, 12 pages), and infrastructure
definitions (Docker images, docker-compose, AWS Terraform). Local
default: SQLite + in-process job runner + mock LLM. Production path:
Postgres+pgvector, OpenAI/Anthropic/Gemini (credential-gated), AWS.

This was **not** a rebuild. The codebase was already substantially real
when this audit started — the job was verifying that claim against the
actual source and fixing what was genuinely broken, not replacing working
design.

## Verified features (actually tested, not assumed)

Everything marked VERIFIED WORKING in `docs/REPOSITORY_AUDIT.md` and
`docs/REQUIREMENTS_TRACEABILITY.md`, including: register/login/JWT auth,
per-user data isolation (DB-level, retrieval-level, agent-level), the
document pipeline (upload → extract → chunk → embed → classify → entities
→ deadlines → graph → READY/FAILED), hybrid search + grounded RAG with
validated citations and a tested prompt-injection defense, recurring-
payment/anomaly/forecast/risk data science with genuine (not fabricated)
statistics, the agent planner/executor/tool registry with a server-
enforced SAFE/SENSITIVE/CONSEQUENTIAL approval gate that a rejection
actually blocks, a real persisted agent trace, an append-only audit
trail, and 12 frontend pages (10 original + Privacy and 404, added in
this audit) that all fetch live data with real loading/error/empty
states.

## Bugs found and fixed in this audit

1. **Missing `email-validator` dependency** — the app could not import
   `app.main` at all without it (`pydantic.EmailStr` in
   `schemas/__init__.py`); CI's `pytest` step would have failed on a
   clean checkout. Added to `apps/api/requirements.txt`.
2. **Ingestion concurrency race** — the 2-thread worker pool processing
   documents for one user in parallel could duplicate-insert the same
   knowledge-graph/deadline/merchant row (no DB constraint backed the
   "get or create" pattern), raising `MultipleResultsFound` and marking
   documents `FAILED` (~1 in 5-10 runs of the full E2E test). Fixed with
   `UniqueConstraint`s + savepoint-scoped retry-on-conflict.
3. **A bug in fix #2's first version** — `db.add()` was called *before*
   entering the `SAVEPOINT`, which left the SQLAlchemy session in a
   `PendingRollbackError` state after the caught conflict, breaking the
   *next* unrelated commit in that session. Found by stress-running the
   full suite after the first fix (not by inspection) and confirmed with
   a standalone 15-line reproduction before and after moving `add()`
   inside the `with db.begin_nested():` block.
4. **`JobRunner` / DB-engine global-singleton test-isolation bug** — a
   second `create_app()` lifespan in the same process (any two test
   modules that each build their own `TestClient`) would silently break
   background job processing (`stop()` never clears the internal
   `threading.Event`, so a restarted runner's threads exit immediately)
   and could point at a stale database (the engine singleton isn't reset
   unless the caller does it explicitly). Reproduced deterministically by
   running two specific test files together in an order the default
   `pytest` suite doesn't use. Fixed at both points.
5. **Non-deterministic demo-data bytes** — `reportlab` stamps
   `/CreationDate`/`/ModDate`/`/ID` with the real wall-clock time by
   default, so regenerating the committed demo PDFs produced different
   bytes on different days even though every visible fact was already
   anchored to a fixed date + seeded RNG. Fixed with `invariant=1`;
   verified two consecutive regenerations are now `md5sum`-identical.
6. **Insecure default JWT secret had no enforcement** — documented as
   "must be set in production" but nothing checked it. Added
   `Settings.assert_production_safe()`, called at app startup, which
   refuses to boot if `NEXUS_ENVIRONMENT=production` and the secret is
   still the `.env.example` default.
7. **Hardcoded CORS wildcard** — made configurable via
   `NEXUS_CORS_ORIGINS`.
8. **Defense-in-depth gap** — an anomaly-endpoint transaction lookup by
   id had no `user_id` filter (not currently exploitable, but relied on
   an invariant that could silently change). Added the filter.
9. **`GeminiProvider.chat()` never attached its API key** to the request
   — the Gemini provider path was non-functional as shipped (fails
   closed with 401 rather than fabricating output, but still a real bug).
10. **`GET /documents` had no pagination** at all, unlike every other list
    endpoint in the API. Added `limit`/`offset`.
11. **Dead code**: an unreachable toast-notification mechanism in
    `Layout.tsx` (state + effect + render block that nothing ever called
    with a message). Removed.
12. **Lint/type hygiene**: one unused import (`ruff`) and one real
    variable-type-reuse issue (`mypy`) in `services/records.py`. Both
    fixed; both tools now report zero issues.
13. **Stale doc comment**: `Makefile`'s `seed` target commented the wrong
    demo email domain (`.local` vs. the actual `.dev`). Fixed.
14. **`GET /notifications` was completely broken** — `NotificationOut`
    inherited from plain `BaseModel` instead of the shared `ORMModel`
    (which sets `from_attributes=True`), so validating real ORM rows
    raised a `pydantic_core.ValidationError` → HTTP 500 on any non-empty
    result. Zero tests ever called this endpoint. **Found by actually
    running the app in a browser** after building the notifications UI
    below — a static-analysis pass would not have caught this. Fixed the
    schema inheritance and added a regression test that uploads a
    document (which generates a real notification) and exercises list/
    mark-read/mark-all-read against a genuinely non-empty result.
15. **Three product areas named in the source brief had no frontend**:
    Notifications (real backend, no UI), Privacy/data-deletion (real
    `DELETE /auth/me`, no UI), and a proper 404 page (unmatched routes
    silently redirected home). Built all three against the existing
    design system and verified live in a browser — see "Verified live in
    a browser" below.
16. **CI's own first real run failed** — the frontend job pinned
    `node-version: "20"`, but `jsdom@30` (pulled in by `vitest`, added in
    this audit) requires Node `^22.22.2 || ^24.15.0 || >=26.0.0` and
    hard-crashes on Node 20 (`TypeError: webidl.util.markAsUncloneable is
    not a function`). The incompatibility was visible in `npm install`'s
    `EBADENGINE` warnings at the time but not acted on, because the local
    dev environment (Node 24) masked it — every prior "the suite passes"
    claim in this audit was true locally and had never actually been run
    through GitHub Actions until the first real push. Caught by checking
    the actual CI run (`gh run view`) after pushing, not assumed from a
    green local terminal. Bumped CI to Node 24 to match the local
    environment exactly; the backend job passed on its first real run
    with zero changes needed.

## Verified live in a browser

Per the rule that UI changes need actual browser verification, not just a
clean build: the API and Vite dev servers were started for real, the demo
dataset was seeded (`scripts/seed_demo.py` — real subscriptions, real
IsolationForest anomalies with explanations, a real HIGH-risk assessment,
a real agent run gated on approval, real RAG eval metrics), and the app
was driven with headless Chromium (Playwright) through: login → dashboard
(real numbers, matches the seed script's own output) → opening the new
notification bell (real unread badge and content) → the new Privacy page
(real per-category counts) → an unknown route (the new 404 page) → a full
register → delete-account → confirm-login-now-fails → confirm-audit-row-
persisted round trip on a disposable throwaway account. Zero browser
console/page errors were observed in the final passing run. This is also
how bug #14 above (a completely broken `/notifications` endpoint) was
caught — it had no test coverage and would not have been found by
`pytest`, `ruff`, `mypy`, or a build check alone.

## Partial features (work, but with a caveat)

- **RAG evaluation service** (`evaluation_service.py`) is exercised
  end-to-end by the E2E test but has no dedicated unit test — a
  regression here would only be caught indirectly.
- **Risk classifier holdout metrics**: real, runtime-computed accuracy/
  recall on a genuine 80/20 split — but only exercised by a unit test,
  not exposed through any API endpoint or the Risk Center UI yet. No
  fabricated number is being shown anywhere; the metric is simply not
  surfaced yet. `docs/data-science.md` corrected to say this precisely.
- **Frontend dependency vulnerabilities** (`npm audit`: esbuild/vite dev-
  server advisories, react-router open-redirect/SSR advisories, and a
  critical `vitest --ui`-only advisory introduced by adding the test
  framework in this audit) — all real, all documented with their exact
  precondition in `docs/security.md`, deliberately deferred (the
  breaking-upgrade ones) or inapplicable-as-used (the `vitest --ui` one)
  rather than silently accepted.

## Simulated features (intentional, clearly labelled)

- `send_email` and `cancel_subscription` agent tools: declared
  INTEGRATION STUBS. Approved execution returns `status: "SIMULATED"`
  with the reason (no SMTP/bank API available offline) and is
  audit-logged. Nothing pretends a real external action occurred.
- Mock LLM mode (`NEXUS_LLM_PROVIDER=mock`, the default): extractive,
  deterministic, explicitly `is_mock=True`. Real providers (OpenAI/
  Anthropic/Gemini) activate only with a credential present and raise
  rather than silently falling back if misconfigured.

## Broken features that could not be fixed

None identified. Every genuine defect found during this audit (listed
above) was root-caused and fixed within this workspace, then re-verified.

## Security

See `docs/security.md` (updated in this audit) and `docs/threat-model.md`
for the full picture. Summary of this pass's findings: one real
enforcement gap closed (production secret-key guard), one hardening item
closed (CORS configurability), one defense-in-depth gap closed (anomaly
endpoint IDOR filter), zero Python dependency vulnerabilities
(`pip-audit`), seven frontend dependency advisories documented with
their exact preconditions (`npm audit` — dev-tooling/breaking-upgrade-
required, or, for the one critical finding, a CLI flag this project
never passes). No
cross-user data access vulnerability was found in the DB/API/RAG/agent
layers reviewed. NEXUS is not claimed to be "100% secure" — residual
risks are listed in `docs/threat-model.md`.

## Testing — actual commands and actual results

All commands below were executed in this workspace during this audit.

```
$ ./.venv/Scripts/python.exe -m pytest -q
.....................................                                    [100%]
37 passed
```

Stress verification (this audit does not claim "works" without repeated
runs for anything that was ever observed flaky):

- The specific two-file combination that exposed the concurrency +
  session bugs (`pytest tests/test_e2e.py apps/api/tests/test_concurrency.py`)
  was run repeatedly after each fix; the final state passed every run
  observed in this session.
- The full suite (`pytest -q`, 37 tests) was run repeatedly with real
  exit-code checking (not string-matching, which was tried first and
  found to be an unreliable check) after the final fix, with zero
  failures across every batch run in this session.

```
$ ruff check .
All checks passed!

$ mypy apps/api/app ml
Success: no issues found in 77 source files

$ pip-audit -r apps/api/requirements.txt
No known vulnerabilities found

$ cd apps/web && npm run lint && npm test && npm run typecheck && npm run build
(all four succeed — ESLint and Vitest were both added in this audit;
neither existed before. Lint found and fixed one real pre-existing
issue in DocumentsPage.tsx; writing the Privacy-page test surfaced a
real label/input accessibility gap, fixed immediately. 13/13 tests pass.)

$ npm audit
7 vulnerabilities (5 moderate, 1 high, 1 critical) — documented in
docs/security.md with each finding's precondition; the critical one
(vitest, GHSA-5xrq-8626-4rwp) only applies to `vitest --ui`, which this
project's `npm test` (`vitest run`) never invokes. Deferred pending a
deliberate major-version upgrade (vite 5→8, react-router-dom 6→7) for
the pre-existing findings.
```

### GitHub Actions — the actual CI run, not just valid YAML

Every result above was run locally in this workspace. Pushing to GitHub and
checking the real workflow run (`gh run view`, not assumed) is a distinct
kind of evidence, and it caught something local runs couldn't: the
**first real CI run failed**. The frontend job's `Unit tests` step
crashed on Node 20 with `jsdom@30` (added this session via `vitest`),
which requires Node `^22.22.2 || ^24.15.0 || >=26.0.0`. Fixed by bumping
CI to Node 24 (bug #16 above). The **backend job passed on its first
real run** with zero changes needed — full toolchain (pytest, ruff,
mypy, pip-audit) green on a genuinely fresh Ubuntu runner, not just this
workspace.

```
$ gh run view <run-id> --repo gopalchaudhary101/nexus
✓ backend   1m24s
X frontend  22s  — Unit tests step: node 20 / jsdom 30 incompatibility
```

## Performance

Only measured items are reported. `npm run build` output sizes: main
bundle 121.55 kB (31.32 kB gzip), react vendor chunk 205.81 kB (65.32 kB
gzip), charts vendor chunk 394.49 kB (107.28 kB gzip). No load/latency
testing was performed against the API in this audit — not claimed.
One real gap was found and fixed: `GET /documents` had no pagination;
it now defaults to 100 rows (max 200).

## Deployment

**Configured, not deployed.** Dockerfiles (`infrastructure/docker/
Dockerfile.{api,web}`) and `docker-compose.yml` were reviewed statically
(non-root user, pinned base image, healthchecks present, no baked-in
secrets) but **not built or run** — Docker was unavailable in this
verification environment. AWS Terraform (`infrastructure/aws/terraform/
main.tf`) was reviewed statically for hardcoded secrets (none found: RDS
uses `manage_master_user_password`, the JWT secret is generated via
`random_string` into Secrets Manager) but **not planned or applied** — no
AWS credentials/environment were available. Neither of these should be
read as "verified working infrastructure"; they are "reviewed source,
unverified at runtime," stated plainly rather than implied otherwise.

## Limitations (honest)

- Scam-risk classifier accuracy/recall are real numbers from real math,
  computed on a small (~90-message) synthetic corpus — meaningful as a
  regression gate, not as a claim about real-world scam-detection
  performance.
- The local hashing-trick embedder is lexical, not semantic — documented
  as such; a real embedding model is a credential-gated swap-in.
- Notifications and Privacy/data-deletion had no frontend when this audit
  started; both were built and verified live in a browser during this
  pass (see "Bugs found and fixed" #15 and "Verified live in a browser").
- No load testing, no penetration testing, no deployed-infrastructure
  verification. This audit reviewed source and ran the available local
  test/build/lint/audit tooling — nothing more is claimed.

## Resume-claim-worthy statements (only what's directly supported)

- Built/maintained a personal-data intelligence platform with a real
  RAG pipeline (hybrid retrieval, validated citations, a tested
  prompt-injection defense) over user documents.
- Implemented genuine ML: Isolation Forest anomaly detection with a
  disclosed fallback, a real Naive Bayes + heuristic risk-scoring
  fusion with runtime-computed holdout metrics, and trend+seasonal
  forecasting with an explicit insufficient-data path.
- Designed and shipped a human-in-the-loop agent approval system with
  server-enforced (not frontend-only) consequential-action gating and a
  full persisted execution trace + append-only audit log.
- Diagnosed and fixed two related concurrency/session-management bugs in
  a multi-threaded background job system (a check-then-insert race
  fixed with DB constraints + SAVEPOINT retry, and a SQLAlchemy
  session-state bug in that same fix caught by stress-testing rather
  than by inspection) — each reproduced deterministically before being
  called fixed.
- Caught a completely broken, zero-test-coverage API endpoint by actually
  running the application in a browser rather than trusting a passing
  test suite and a clean build — and fixed it with a schema change plus a
  regression test that exercises a genuinely non-empty result.

## Completion gate

Every box in the source instruction's completion checklist was walked
against this audit's actual findings; the handful that remain unchecked
are listed explicitly as PARTIAL/NOT VERIFIED above and in
`docs/REQUIREMENTS_TRACEABILITY.md`, with the reason given, rather than
silently marked done. Nothing in this document claims a capability that
was not exercised in this workspace.
