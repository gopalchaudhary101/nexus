# NEXUS — Deployment

Two supported targets: **local development** (no cloud, no Docker needed)
and **AWS production** (primary cloud; Terraform + Docker).

## 1. Local development

```bash
make install          # pip deps
make demo             # synthetic dataset + demo user (demo@nexus.dev)
uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000
make web-install && cd apps/web && npm run dev   # :5173, proxies /api
```

- Database: SQLite at `data/processed/nexus.db` (auto-created).
- LLM: `mock` (declared deterministic mode) · Embeddings: `hash` (offline).
- Jobs: in-process threaded runner (no Redis/Celery).
- Login: `demo@nexus.dev` / `nexus-demo-2026` (override with
  `NEXUS_DEMO_PASSWORD` at seed time).

Switch providers without code changes (env, see `.env.example`):

```bash
NEXUS_LLM_PROVIDER=openai NEXUS_OPENAI_API_KEY=... NEXUS_LLM_MODEL=gpt-4o-mini
NEXUS_EMBED_PROVIDER=openai NEXUS_EMBED_MODEL=text-embedding-3-small
NEXUS_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/nexus
NEXUS_USE_PGVECTOR=1        # serve vector search from Postgres
```

## 2. Docker (local or staging)

```bash
docker compose up --build     # pgvector pg16 + api + web
```

- `infrastructure/docker/api.Dockerfile` — python:3.13-slim, installs
  pinned requirements, runs uvicorn (non-root).
- `infrastructure/docker/web.Dockerfile` — node:20-alpine build stage →
  nginx:alpine serving `dist/` with `/api` proxied to the api service.
- Compose wires `NEXUS_DATABASE_URL` to the pgvector service and creates
  the `vector` extension on startup (requires superuser in the init step).

## 3. AWS production architecture

```mermaid
flowchart LR
  subgraph Edge
    CF[CloudFront + WAF]
  end
  subgraph VPC
    ALB[ALB - TLS 1.2+]
    subgraph Public
      EB[EC2/ECS t3.micro<br/>web static fallback]
    end
    subgraph Private
      F1[ECS Fargate task<br/>nexus-api:8000]
      F2[ECS Fargate task<br/>nexus-api:8000]
      RDS[(RDS PostgreSQL 16<br/>+ pgvector, Multi-AZ)]
      SQS[SQS job queue]
      SECM[Secrets Manager]
    end
    S3[(S3 uploads<br/>private, versioned, SSE)]
  end
  CW[CloudWatch<br/>logs + alarms]

  CF --> ALB
  ALB --> F1 & F2
  F1 & F2 --> RDS
  F1 & F2 --> S3
  F1 & F2 --> SECM
  F1 & F2 -. "long jobs (prod path)" .-> SQS
  F1 & F2 --> CW
```

**Choices & why**
- **CloudFront + WAF** in front of everything (CSP, rate rules, geo).
- **ALB** terminates TLS; the API is stateless → scale behind it.
- **ECS Fargate** (not EC2) for the API: versioned task definitions,
  rolling deploys, no patching.
- **RDS PostgreSQL 16 + pgvector**: relational core *and* vector search in
  one engine — no separate vector DB (per spec).
- **S3** for raw uploads (the local upload dir is the same seam).
- **SQS** is the production path for long ingestion/eval jobs behind the
  same `JobRunner.submit` interface (local mode = thread pool).
- **Secrets Manager** for `NEXUS_SECRET_KEY`, DB password, provider keys;
  injected as task env at startup.
- **CloudWatch**: container logs, API access logs, alarms on 5xx/latency,
  RDS storage/read-replica metrics.

### Terraform

`infrastructure/aws/terraform/` provisions: VPC (2 public / 2 private
subnets), ECS cluster + service (Fargate, 2 tasks), RDS instance
(pgvector-capable engine + extension), S3 bucket, SQS queue, Secrets
Manager secret, ALB + listener, IAM roles (task execution/task role with
least privilege), CloudWatch log group + alarm.

```bash
aws s3 mb s3://nexus-tfstate-<account> --region <region>
cd infrastructure/aws/terraform
terraform init -backend-config="bucket=nexus-tfstate-<account>"
terraform apply
```

### Environment (production)

```
NEXUS_DATABASE_URL=postgresql+psycopg://$(nexus_user):<from-secret>@<rds-host>/nexus
NEXUS_USE_PGVECTOR=1
NEXUS_SECRET_KEY=<from-secret>
NEXUS_LLM_PROVIDER=openai   NEXUS_OPENAI_API_KEY=<from-secret>
NEXUS_EMBED_PROVIDER=openai
NEXUS_HOST=0.0.0.0  NEXUS_PORT=8000
NEXUS_UPLOAD_DIR=s3://nexus-uploads   (S3-backed storage adapter)
```

## 4. Operational runbooks (short)

| incident | action |
|---|---|
| token leak suspected | rotate `NEXUS_SECRET_KEY` → all tokens invalidated; roll tasks |
| ingestion stuck | check CloudWatch for the job id; `FAILED` docs carry the reason in `status_detail` |
| Postgres connection pool exhaustion | raise `max_connections` / add pgbouncer (future); pool_pre_ping is on |
| bad LLM provider config | API returns an explicit 500 with reason (never silent fallback) |

## 5. What is NOT automated yet (honest scope)

- The S3-backed storage adapter (local dir works; the seam is
  `services/storage.py`).
- pgbouncer, read replicas, autoscaling targets.
- Multi-region DR.
