# NEXUS — Security Implementation

## Authentication & sessions

- **Passwords**: PBKDF2-HMAC-SHA256, 200k iterations, per-password 16-byte
  salt, constant-time compare. (Argon2id recommended at >1k users; the
  hashing interface is isolated in `core/security.py` for a one-file swap.)
- **Tokens**: HS256 JWT, 8h TTL, `jti` per token. `NEXUS_SECRET_KEY`
  must be set in production (Secrets Manager in AWS). **Enforced, not just
  documented**: `Settings.assert_production_safe()` (`core/config.py`),
  called from `create_app()`, refuses to start when
  `NEXUS_ENVIRONMENT=production` and the secret is still the insecure
  `.env.example` default — a prior gap where this was advisory-only would
  have let anyone forge a valid token for any user id if deployed unchanged.
- **Rate limiting**: fixed-window per-IP limiter on register/login
  (default 30/min; process-local — Redis behind the same interface in
  multi-instance deployments).
- **Errors**: generic "Invalid email or password" (no user enumeration via
  login failures), no stack-trace leaks (500 handler returns a fixed body).

## Data isolation (per-user tenancy)

- Every query in routers/services is filtered by the authenticated user's
  id; document fetch by id returns 404 for other users' documents
  (existence is not leaked beyond the fetch itself).
- Retrieval (RAG) is **always** filtered by `user_id` — a user can never
  retrieve another user's chunks.
- Graph, memory, notifications, approvals and audit rows are all
  user-scoped; cross-user access is impossible through the API.
- Tested: `tests/test_api_core.py::test_user_isolation`.

## Upload handling (untrusted input)

- Extension allowlist (pdf, docx, txt, md, csv, png, jpg, jpeg, webp).
- **Magic-byte sniffing must agree with the extension family**
  (PDF/ZIP) — mismatched content is rejected.
- UTF-8 validity check for text formats.
- Size cap (default 10 MB, configurable).
- Filenames sanitised (`safe_filename`) **before any path join** —
  traversal-safe; uploads land in `uploads/{user_id}/{doc_id}/`.
- Stored bytes are re-read only by the ingestion pipeline; text is
  extracted, never executed.

## RAG / prompt-injection defense

- Retrieved document text is wrapped in labelled `<context>` blocks and
  the system prompt declares it **untrusted data, never instructions**.
- Answers must be grounded: refusals return confidence 0 and no sources;
  hallucinated citations (LLM mode) are validated out against retrieved
  refs.
- Tool outputs are passed to the synthesizer as structured data, never as
  raw prompt text.
- Tested: `test_prompt_injection_in_document_is_data`.

## Agent action control

- Tools are the only execution path (no shell/eval/arbitrary SQL).
- Risk classes: SAFE auto, SENSITIVE approval, CONSEQUENTIAL explicit
  approval; unknown tools fail closed to ASK.
- External-world tools (send_email, cancel_subscription) are declared
  integration stubs: approved execution returns an explicit
  `SIMULATED` result with the reason and is audit-logged. Nothing is
  faked.
- Full audit trail: `audit_events` is append-only.

## Secrets & environment

- All configuration via `NEXUS_*` env vars (`.env.example` documents the
  set). No secrets in code or in the repo.
- LLM/embedding providers activate **only** when credentials are present;
  otherwise the declared mock/local modes run. Misconfiguration (provider
  set, key missing) raises an explicit error rather than silently falling
  back.

## CORS / transport

- Dev CORS (`NEXUS_CORS_ORIGINS=*`) is open for local tooling; **production
  must set `NEXUS_CORS_ORIGINS`** to a comma-separated list of the real
  frontend origin(s) (`main.py` reads `Settings.cors_origin_list`) and
  terminate TLS at the ALB/CloudFront (see `docs/deployment.md`). No
  cookies/credentials are sent (`allow_credentials=False`), so the wildcard
  default carries no session-hijack risk in local dev — it is purely a
  production-hardening step, not a currently-exploitable gap.
- JWTs travel in `Authorization: Bearer` headers.

## Data-integrity note (concurrency)

- The ingestion worker pool (`NEXUS_WORKER_THREADS`, default 2) processes
  multiple documents for the same user in parallel. The knowledge-graph,
  deadline and merchant "get-or-create" helpers were a plain
  check-then-insert with no DB constraint backing them, so two documents
  ingested at the same instant could race to insert the same row (most
  visibly the singleton per-user `USER` graph node), and a later lookup
  would raise `MultipleResultsFound` and mark that document `FAILED`. Not a
  cross-tenant leak (each race was scoped to a single user's own rows), but
  a real reliability bug, reproduced via `tests/test_e2e.py` (~1 in 5-10
  runs) and now via the deterministic
  `apps/api/tests/test_concurrency.py`. **Fixed**: unique constraints on
  `KnowledgeEntity(user_id, kind, name)`, `Deadline(user_id, title,
  due_date)` and `Merchant(user_id, normalized)`, with the insert wrapped
  in a `SAVEPOINT` that catches the loser's `IntegrityError` and re-selects
  the winner's row instead of crashing the job.

## Dependency note

- Production Python dependencies are pinned in `apps/api/requirements.txt`;
  `pip-audit -r apps/api/requirements.txt` was run during this review and
  found **no known vulnerabilities**.
- Frontend (`apps/web`): `npm audit` reports 4 findings (3 moderate, 1
  high), all in dev/transitive tooling, not runtime app code:
  - `esbuild <=0.24.2` (via `vite`) — dev-server request-forgery advisory;
    affects `vite dev` only, not the production `dist/` build served by
    nginx.
  - `react-router` 6.0.0–7.17.0 (the app pins `^6.28.0`) — an open-redirect
    advisory and an SSR-hydration advisory; NEXUS is a client-only SPA
    (no server-side rendering), so the SSR advisory does not apply, and no
    user-controlled redirect target is passed to `<Link>`/`useNavigate`
    anywhere in `apps/web/src`.
  - The fix for both requires a breaking major-version upgrade (`vite` 5→8,
    `react-router-dom` 6→7). Deferred rather than forced blind, per the
    "no blind rewrites" policy — flagged here as a known, accepted-risk
    finding for a deliberate, tested upgrade rather than an undisclosed gap.
- CI (`.github/workflows/ci.yml`) runs tests + ruff + mypy on every PR;
  `pip-audit`/`npm audit` are recommended CI additions, not yet wired in.
