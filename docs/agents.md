# NEXUS — Agentic Workflows

## Design

NEXUS agents are **evidence-first and approval-gated**. The loop:

observe → understand → retrieve evidence → analyze → predict → explain →
propose → **ask permission** → act safely.

- **Planner** (`agents/planner.py`): deterministic rule planner. Maps the
  request to an intent (`weekly_attention`, `expiring_soon`,
  `subscription_review`, `risk_check`, `anomaly_review`, `forecast`,
  `spending_change`, `rag_question`) and a declared list of tool steps.
  It is documented as pluggable — an LLM planner can be swapped in behind
  the same `(intent, steps)` interface.
- **Tools** (`agents/tools.py`): the *only* way an agent touches data.
  No shell, no eval, no arbitrary SQL — every tool is a fixed Python
  function with declared parameters and a risk class.
- **Executor** (`agents/executor.py`): runs the plan, records every step
  (type, name, real args, real result, duration, status), streams real
  execution events over SSE, and pauses on the first gated tool.
- **Memory** (`agents/memory.py`): scoped, user-owned key/value memory
  (conversation window, preferences, state). Nothing is stored blindly;
  `wipe_user_memory` runs on account deletion.

## Tool registry & risk classes (spec §39–42)

| tool | risk | behaviour |
|---|---|---|
| search_documents | SAFE | hybrid retrieval over user's docs |
| get_document | SAFE | metadata + preview |
| search_transactions | SAFE | history by time/amount |
| list_subscriptions | SAFE | detected subscriptions |
| detect_anomalies | SAFE | fits+runs anomaly model (needs ≥8 txns, else explicit message) |
| list_deadlines | SAFE | deadlines + computed risk level |
| get_forecast | SAFE | forecast or explicit insufficient-data |
| analyze_risk | SAFE | multi-signal risk engine |
| build_insight_report | SAFE | prioritized aggregation |
| create_reminder | SENSITIVE | creates a task — **needs approval** |
| prepare_email | SENSITIVE | saves a draft (never sends) — **needs approval** |
| send_email | CONSEQUENTIAL | **integration stub**: approved execution returns an explicit `SIMULATED` result ("SMTP not configured — no email was sent"), audit-logged |
| cancel_subscription | CONSEQUENTIAL | **integration stub**: returns an explicit `SIMULATED` result; nothing is ever cancelled |
| delete_document | CONSEQUENTIAL | real delete of the user's own document + derived data, audit-logged |

Default policy for unknown tools: **ASK** (fail-closed).

## Human-in-the-loop flow

```
run_agent:
  1. record PLANNER step (intent + full plan)
  2. execute SAFE tools → TOOL steps (real result summary, duration)
  3. on first SENSITIVE/CONSEQUENTIAL tool:
       create Approval (PENDING), record GATE step (PENDING_APPROVAL),
       persist progress in the run, set status WAITING_APPROVAL,
       notify the user, stream {gate} event, pause
  resume_after_approval:
       approve → execute tool (or mark FAILED), mark approval EXECUTED,
                 continue remaining plan steps (further gates possible)
       reject  → record GATE step SKIPPED, mark approval REJECTED,
                 continue remaining steps
  4. synthesize response from tool evidence (deterministic in mock mode)
     → REPORT step, status COMPLETED, audit event, notification,
     stream {final, done}
```

Only real execution states are ever emitted — there is no fake progress
animation. A paused run stays paused until a human decides; the Approvals
page shows the exact tool, args and risk class.

## Audit

Every consequential event is appended to `audit_events`
(append-only; the app never updates or deletes rows): auth, uploads,
deletes, approval requests/decisions, tool executions, simulated
integrations, agent runs, eval runs, account deletion.

## Memory policy

- conversation: last 10 requests (rolling), scoped per user
- preference: explicit key/value preferences
- state: scratch task state
- deletion: `DELETE /auth/me` wipes user data **and** memory entries
