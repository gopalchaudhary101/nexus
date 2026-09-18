# NEXUS — Threat Model

Strategic (not exhaustive) threat model: assets, threat classes, controls,
residual risk. Personas: external attacker, compromised client, malicious
document content, malicious message content, insider.

## Assets

| asset | value | primary controls |
|---|---|---|
| User personal data (documents, transactions, messages) | High | encryption in transit (TLS at edge), at rest (volume/EBS + S3 SSE), per-user isolation, upload validation |
| Authentication state | High | PBKDF2 password hashing, short-TTL JWT, rate limiting |
| Approval decisions / audit trail | High | append-only audit table, explicit state machine, per-user scoping |
| Model/eval artifacts | Medium | stored per user, computed at runtime |
| Availability | Medium | stateless API (scale out), Postgres managed (RDS), backups |

## Threat classes & controls

### T1 — Credential theft / brute force
- **Control**: 200k-iteration PBKDF2, per-IP fixed-window rate limit on
  auth endpoints, generic failure messages.
- **Residual**: offline cracking of a leaked DB dump is still possible;
  argon2id + breach-list checks recommended at scale.

### T2 — Session hijack / token replay
- **Control**: 8h TTL JWTs with `jti`; tokens bound to a per-deployment
  secret. Revocation = rotate `NEXUS_SECRET_KEY` (documented operational
  procedure; a token allowlist is a possible extension).
- **Residual**: a stolen token is valid until expiry or rotation.

### T3 — Cross-tenant data access
- **Control**: every data access path (SQL queries, retrieval, graph,
  memory) filters by the authenticated `user_id`; id fetches 404 for
  foreign objects. Covered by isolation tests.
- **Residual**: a future bug bypassing a filter is the main risk; the
  filter pattern is uniform and test-covered.

### T4 — Malicious document content (prompt injection / data exfiltration via RAG)
- **Control**: retrieved content is untrusted data in labelled blocks;
  system prompt forbids treating it as instructions; answers must be
  grounded or refused; citations validated. Mock mode is extractive, so a
  malicious document can only surface its own text as a quoted answer —
  it cannot exfiltrate other users' data (isolation) or change agent
  behaviour (agents only call declared tools).
- **Residual**: in LLM mode, a sophisticated injection could influence the
  *phrasing* of a grounded answer; it cannot bypass tenant isolation or
  invoke tools.

### T5 — Malicious message content (risk engine manipulation)
- **Control**: the risk engine treats message text as data; outputs are
  risk assessments with disclaimers; no message content is ever executed
  or interpreted as instructions.
- **Residual**: evasion of heuristics/NB is possible (by design — triage,
  not a guarantee).

### T6 — Upload attacks (traversal, polyglot, resource exhaustion)
- **Control**: extension allowlist, magic-byte/extension agreement, UTF-8
  check, size cap, filename sanitisation before path join, per-user
  directory isolation.
- **Residual**: parsers (pypdf/python-docx) are third-party; keep
  dependencies current.

### T7 — Agent abuse (unauthorised actions)
- **Control**: fixed tool registry (no code execution), risk classes with
  approval gates (fail-closed default), external-world tools are declared
  simulation stubs in this deployment, full audit trail of executions and
  decisions.
- **Residual**: an approved SIMULATED action could be mistaken for a real
  one — mitigated by explicit `SIMULATED` status, reason text and audit
  rows.

### T8 — Supply chain / dependencies
- **Control**: pinned requirements, CI runs tests + ruff + mypy on every
  PR, Docker images built from versioned requirements.
- **Residual**: transitive dependency CVEs between scans; run
  `pip-audit`/Dependabot in CI for production.

### T9 — Infrastructure (AWS)
- **Control** (see `docs/deployment.md` + `infrastructure/aws/terraform`):
  VPC-private subnets for API/DB, security groups (no public DB), S3
  bucket private + versioned, Secrets Manager for credentials, CloudFront
  + WAF in front of the web app, ALB TLS termination, RDS multi-AZ with
  automated backups, CloudWatch alarms.
- **Residual**: misconfiguration risk during manual changes; Terraform is
  the single source of truth.

## Explicit non-goals

- NEXUS does not store full card numbers or OTPs; transaction CSVs are
  user-provided data.
- No PII is used to train shared models; all models run per-user on the
  user's own data.
- Demo data is synthetic and committed — no real personal data in the repo.
