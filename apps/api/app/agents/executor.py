"""Agent executor: planner -> policy gate -> tools -> approval resume.

Flow
    1. Record PLANNER step (intent + plan).
    2. Execute SAFE tools immediately, recording each TOOL step with real
       args, result summary, duration and status. Only real execution states
       are emitted (no fake progress).
    3. On the first SENSITIVE/CONSEQUENTIAL tool: create an Approval, record
       a GATE step (PENDING_APPROVAL), persist progress, and pause the run
       (WAITING_APPROVAL).
    4. On approve/reject (approvals API) the run resumes: the gated tool
       runs (or is skipped), remaining steps execute, and the run completes
       with a synthesized, evidence-backed response.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit.service import log as audit_log
from ..db.models import AgentRun, AgentStep, Approval
from ..services.notify import notify
from . import memory
from .planner import PlanStep, build_plan, classify_intent
from .policies import SAFE
from .state import (
    RUN_COMPLETED,
    RUN_RUNNING,
    RUN_WAITING_APPROVAL,
    STEP_FAILED,
    STEP_OK,
    STEP_PENDING_APPROVAL,
    STEP_SKIPPED,
)
from .tools import TOOLS


def _summarize(value: dict, limit: int = 240) -> str:
    try:
        s = json.dumps(value, default=str)
    except (TypeError, ValueError):
        s = str(value)
    return s[:limit] + ("…" if len(s) > limit else "")


def _record_step(db: Session, run: AgentRun, seq: int, stype: str, name: str,
                 detail: str, status: str, args: dict | None = None,
                 result: dict | None = None, duration_ms: float = 0.0) -> AgentStep:
    step = AgentStep(
        run_id=run.id, user_id=run.user_id, seq=seq, type=stype, name=name,
        detail=detail, status=status,
        args_json=json.dumps(args or {}, default=str),
        result_json=json.dumps(result if result is not None else {}, default=str),
        duration_ms=round(duration_ms, 1),
    )
    db.add(step)
    db.commit()
    return step


def _persist_progress(run: AgentRun, results: dict, plan: list[PlanStep],
                      next_index: int) -> None:
    run.result_json = json.dumps({
        "results": {k: v for k, v in results.items()},
        "plan": [{"tool": s.tool, "args": s.args, "description": s.description} for s in plan],
        "next_index": next_index,
        "intent": run.intent,
    }, default=str)


def _synthesize(intent: str, results: dict, request: str) -> str:
    parts: list[str] = []
    rep = results.get("build_insight_report", {})
    dl = rep.get("high_priority_deadlines", [])
    if dl:
        lines = [f"• {d['title']} — due {d['due_date']} ({d['days_remaining']}d, {d['risk_level']})"
                 for d in dl[:5]]
        parts.append("Needs attention:\n" + "\n".join(lines))
    open_risks = rep.get("open_risks", [])
    if open_risks:
        lines = [f"• {r['level']} risk: {r['subject'][:80]} (score {r['score']})"
                 for r in open_risks[:5]]
        parts.append("Risk signals:\n" + "\n".join(lines))
    risk = results.get("analyze_risk")
    if risk:
        parts.append(f"Message risk: {risk['risk_level']} (score {risk['score']}). "
                     f"Signals: " + "; ".join(s["label"] for s in risk.get("signals", [])[:5]) +
                     ". " + risk.get("disclaimer", ""))
    subs = rep.get("subscriptions") or results.get("list_subscriptions", {}).get("subscriptions", [])
    if subs:
        top = sorted(subs, key=lambda s: s.get("annualized_cost", 0), reverse=True)[:5]
        lines = [f"• {s['merchant']} — {s['amount']} {s.get('currency', 'INR')} {s['frequency'].lower()}"
                 f" (~{s['annualized_cost']:.0f}/yr, {s['status']}, conf {s['confidence']})"
                 for s in top]
        parts.append("Subscriptions (by annual cost):\n" + "\n".join(lines))
    anom = results.get("detect_anomalies", {})
    if anom.get("ok") and anom.get("flagged"):
        lines = [f"• {f['description'][:60]} — {f['amount']} on {f['date'][:10]} "
                 f"({f['label']}, score {f['score']})" for f in anom["flagged"][:5]]
        parts.append("Unusual transactions (anomaly ≠ fraud — review recommended):\n" + "\n".join(lines))
    elif anom.get("message"):
        parts.append(f"Anomaly detection: {anom['message']}")
    fc = results.get("get_forecast")
    if fc:
        if fc.get("ok"):
            pts = "; ".join(f"{p['month']}: {p['value']:.0f} [{p['lo']:.0f}–{p['hi']:.0f}]"
                            for p in fc.get("points", []))
            parts.append(f"Forecast: {pts}. {fc.get('message', '')}")
        else:
            parts.append(f"Forecast: {fc.get('message', 'Not enough data.')}")
    hits = results.get("search_documents", {}).get("hits", [])
    if hits:
        lines = [f"• {h['document']} — {h['ref']} (score {h['score']}): {h['excerpt'][:160]}"
                 for h in hits[:3]]
        parts.append("Relevant document evidence:\n" + "\n".join(lines))
    if not parts:
        parts.append("I ran the requested checks and found nothing requiring immediate action "
                     "in your current data.")
    parts.append("All items above come from your uploaded data; verify before any consequential action.")
    return "\n\n".join(parts)


def run_agent(db: Session, user_id: str, request: str,
              message: str | None = None,
              stream: Callable[[dict], None] | None = None) -> AgentRun:
    memory.record_request(db, user_id, request)
    intent = classify_intent(request, has_message=bool(message and message.strip()))
    intent, plan = build_plan(intent, request, message)

    run = AgentRun(user_id=user_id, request=request, intent=intent,
                   status=RUN_RUNNING)
    db.add(run)
    db.commit()

    seq = 0
    _record_step(db, run, seq, "PLANNER", "intent_classification",
                 f"Intent: {intent} → {len(plan)} tool step(s)",
                 STEP_OK, args={"request": request[:400]})
    seq += 1
    if stream:
        stream({"type": "planner", "intent": intent, "steps": [s.tool for s in plan]})

    results: dict = {}
    paused_at: int | None = None
    for i, st in enumerate(plan):
        spec = TOOLS.get(st.tool)
        if spec is None:
            _record_step(db, run, seq, "TOOL", st.tool, "Unknown tool", STEP_FAILED)
            seq += 1
            continue
        if spec.risk_class != SAFE:
            approval = Approval(
                user_id=user_id, run_id=run.id, tool=st.tool,
                risk_class=spec.risk_class, args_json=json.dumps(st.args, default=str),
            )
            db.add(approval)
            db.commit()
            _record_step(db, run, seq, "GATE", f"approval_gate:{st.tool}",
                         f"{spec.risk_class} action requires your approval: {st.description}",
                         STEP_PENDING_APPROVAL, args=st.args,
                         result={"approval_id": approval.id})
            seq += 1
            paused_at = i
            _persist_progress(run, results, plan, i)
            run.status = RUN_WAITING_APPROVAL
            db.commit()
            audit_log(db, user_id, "approval.requested", actor="agent",
                      target=st.tool, detail={"approval_id": approval.id})
            notify(db, user_id, "APPROVAL",
                   f"Approval needed: {st.description}",
                   f"Tool {st.tool} [{spec.risk_class}]. Approve or reject in the Approvals page.",
                   "WARN")
            if stream:
                stream({"type": "gate", "tool": st.tool, "approval_id": approval.id,
                        "risk_class": spec.risk_class})
            break

        t0 = time.perf_counter()
        try:
            res = spec.fn(db, user_id, **st.args)
            dur = (time.perf_counter() - t0) * 1000
            status = STEP_OK
            detail = st.description or spec.description
            if isinstance(res, dict) and res.get("message"):
                detail = str(res["message"])
            _record_step(db, run, seq, "TOOL", st.tool, detail, status,
                         args=st.args, result=res if isinstance(res, dict) else {"value": str(res)},
                         duration_ms=dur)
            seq += 1
            results[st.tool] = res if isinstance(res, dict) else {"value": str(res)}
            if stream:
                stream({"type": "tool", "tool": st.tool, "status": "OK",
                        "summary": _summarize(res, 160) if isinstance(res, dict) else str(res)[:160]})
        except Exception as e:  # noqa: BLE001 - a failing tool must not kill the run
            dur = (time.perf_counter() - t0) * 1000
            _record_step(db, run, seq, "TOOL", st.tool,
                         f"Tool failed: {type(e).__name__}: {e}", STEP_FAILED,
                         args=st.args, duration_ms=dur)
            seq += 1
            results[st.tool] = {"error": str(e)}
            if stream:
                stream({"type": "tool", "tool": st.tool, "status": "FAILED",
                        "summary": str(e)[:160]})

    if paused_at is not None:
        return run

    # final synthesis (deterministic in mock mode; LLM provider would be used
    # here when configured — same evidence, no invented facts)
    response = _synthesize(intent, results, request)
    run.status = RUN_COMPLETED
    run.response_text = response
    _persist_progress(run, results, plan, len(plan))
    run.finished_at = datetime.now(UTC)
    _record_step(db, run, seq, "REPORT", "synthesize_response",
                 "Assembled response from tool evidence", STEP_OK,
                 result={"response_chars": len(response)})
    seq += 1
    db.commit()
    audit_log(db, user_id, "agent.run_completed", actor="agent", target=run.id,
              detail={"intent": intent, "steps": len(plan)})
    notify(db, user_id, "AGENT", "Agent finished",
           f"“{request[:80]}” completed with {len(plan)} tool step(s).", "INFO")
    if stream:
        stream({"type": "final", "response": response})
    return run


def resume_after_approval(db: Session, approval: Approval, approved: bool) -> AgentRun | None:
    from datetime import datetime

    run = db.get(AgentRun, approval.run_id) if approval.run_id else None
    if run is None or run.status != RUN_WAITING_APPROVAL:
        return run
    progress = json.loads(run.result_json or "{}")
    plan = [PlanStep(s["tool"], s.get("args", {}), s.get("description", ""))
            for s in progress.get("plan", [])]
    results = progress.get("results", {})
    intent = progress.get("intent", run.intent)
    run.status = RUN_RUNNING
    db.commit()

    seq = max([s.seq for s in db.execute(select(AgentStep).where(AgentStep.run_id == run.id))
               .scalars().all()], default=-1) + 1

    # execute or skip the gated tool
    spec = TOOLS.get(approval.tool)
    if approved and spec is not None:
        t0 = time.perf_counter()
        try:
            res = spec.fn(db, run.user_id, **json.loads(approval.args_json or "{}"))
            dur = (time.perf_counter() - t0) * 1000
            _record_step(db, run, seq, "TOOL", approval.tool,
                         "Executed after user approval", STEP_OK,
                         args=json.loads(approval.args_json or "{}"),
                         result=res if isinstance(res, dict) else {"value": str(res)},
                         duration_ms=dur)
            results[approval.tool] = res if isinstance(res, dict) else {"value": str(res)}
            approval.status = "EXECUTED"
            approval.result_json = json.dumps(res, default=str)
        except Exception as e:  # noqa: BLE001
            _record_step(db, run, seq, "TOOL", approval.tool,
                         f"Tool failed: {type(e).__name__}: {e}", STEP_FAILED,
                         duration_ms=(time.perf_counter() - t0) * 1000)
            approval.status = "FAILED"
            approval.result_json = json.dumps({"error": str(e)})
    else:
        label = "Rejected by user — action not executed" if approved is False else "Approval expired"
        _record_step(db, run, seq, "GATE", f"approval_gate:{approval.tool}",
                     label, STEP_SKIPPED, args=json.loads(approval.args_json or "{}"))
        approval.status = "REJECTED"
    approval.decided_at = datetime.now(UTC)
    db.commit()
    seq += 1

    # continue with remaining plan steps
    start = progress.get("next_index", 0) + 1
    paused_at = None
    for i in range(start, len(plan)):
        st = plan[i]
        spec2 = TOOLS.get(st.tool)
        if spec2 is None:
            seq += 1
            continue
        if spec2.risk_class != SAFE:
            ap = Approval(user_id=run.user_id, run_id=run.id, tool=st.tool,
                          risk_class=spec2.risk_class,
                          args_json=json.dumps(st.args, default=str))
            db.add(ap)
            db.commit()
            _record_step(db, run, seq, "GATE", f"approval_gate:{st.tool}",
                         f"{spec2.risk_class} action requires approval", STEP_PENDING_APPROVAL,
                         args=st.args, result={"approval_id": ap.id})
            seq += 1
            paused_at = i
            _persist_progress(run, results, plan, i)
            run.status = RUN_WAITING_APPROVAL
            db.commit()
            break
        t0 = time.perf_counter()
        try:
            res = spec2.fn(db, run.user_id, **st.args)
            _record_step(db, run, seq, "TOOL", st.tool,
                         st.description or spec2.description, STEP_OK,
                         args=st.args, result=res if isinstance(res, dict) else {"value": str(res)},
                         duration_ms=(time.perf_counter() - t0) * 1000)
            results[st.tool] = res if isinstance(res, dict) else {"value": str(res)}
        except Exception as e:  # noqa: BLE001
            _record_step(db, run, seq, "TOOL", st.tool,
                         f"Tool failed: {type(e).__name__}: {e}", STEP_FAILED,
                         duration_ms=(time.perf_counter() - t0) * 1000)
            results[st.tool] = {"error": str(e)}
        seq += 1

    if paused_at is None:
        run.status = RUN_COMPLETED
        run.response_text = _synthesize(intent, results, run.request)
        _persist_progress(run, results, plan, len(plan))
        run.finished_at = datetime.now(UTC)
        _record_step(db, run, seq, "REPORT", "synthesize_response",
                     "Assembled response from tool evidence", STEP_OK)
        db.commit()
    return run
