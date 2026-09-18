# NEXUS — Security Implementation

## Authentication & sessions

- **Passwords**: PBKDF2-HMAC-SHA256, 200k iterations, per-password 16-byte
  salt, constant-time compare. (Argon2id recommended at >1k users; the
  hashing interface is isolated in `core/security.py` for a one-file swap.)
- **Tokens**: HS256 JWT, 8h TTL, `jti` per token. `NEXUS_SECRET_KEY`
  must be set in production (Secrets Manager in AWS).
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

- Dev CORS is open for local tooling; **production must pin the browser
  origin** and terminate TLS at the ALB/CloudFront (see
  `docs/deployment.md`).
- JWTs travel in `Authorization: Bearer` headers.

## Dependency note

- Production dependencies are pinned in `apps/api/requirements.txt`;
  `pip-audit`/Dependabot-style scanning is part of the CI recommendation
  (`.github/workflows/ci.yml` runs tests + lint + types).
