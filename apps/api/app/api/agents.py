from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.executor import run_agent
from ..core.errors import NotFound
from ..db.models import AgentRun, AgentStep
from ..db.session import get_db
from ..schemas import AgentRunIn, AgentStepOut, AgentTaskListOut, AgentTaskOut
from .deps import get_current_user

router = APIRouter(prefix="/agent", tags=["agent"])


def _step_out(s: AgentStep) -> AgentStepOut:
    return AgentStepOut(
        seq=s.seq, type=s.type, name=s.name, detail=s.detail, status=s.status,
        duration_ms=s.duration_ms,
        args=json.loads(s.args_json or "{}"), result=json.loads(s.result_json or "{}"),
        created_at=s.created_at,
    )


def _task_out(r: AgentRun, db: Session, with_steps: bool = True) -> AgentTaskOut:
    steps = []
    if with_steps:
        steps = [_step_out(s) for s in db.execute(
            select(AgentStep).where(AgentStep.run_id == r.id).order_by(AgentStep.seq)
        ).scalars().all()]
    try:
        result = json.loads(r.result_json or "{}")
    except ValueError:
        result = {}
    result.pop("plan", None)  # keep internal plan out of the public result
    return AgentTaskOut(
        id=r.id, request=r.request, intent=r.intent, status=r.status,
        response_text=r.response_text, result=result,
        created_at=r.created_at, finished_at=r.finished_at, steps=steps,
    )


@router.post("/run")
def run(body: AgentRunIn, db: Session = Depends(get_db),
        user=Depends(get_current_user)):
    """Execute an agent run, streaming real execution events (SSE).

    Events reflect actual execution state only: planner, each tool with its
    real result/summary, approval gates, and the final response.
    """
    def event_stream():
        queue: list[str] = []

        def stream(evt: dict) -> None:
            queue.append(f"data: {json.dumps(evt, default=str)}\n\n")

        run = run_agent(db, user.id, body.request, message=body.message,
                        stream=stream)
        yield from queue
        yield f"data: {json.dumps({'type': 'done', 'run_id': run.id, 'status': run.status})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/tasks", response_model=AgentTaskListOut)
def tasks(limit: int = Query(default=20, ge=1, le=100),
          offset: int = Query(default=0, ge=0),
          db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(AgentRun).where(AgentRun.user_id == user.id)
                      .order_by(AgentRun.created_at.desc())
                      .limit(limit).offset(offset)).scalars().all()
    return AgentTaskListOut(
        items=[_task_out(r, db, with_steps=False) for r in rows], total=len(rows))


@router.get("/tasks/{run_id}", response_model=AgentTaskOut)
def task(run_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.get(AgentRun, run_id)
    if r is None or r.user_id != user.id:
        raise NotFound("Agent run not found")
    return _task_out(r, db, with_steps=True)
