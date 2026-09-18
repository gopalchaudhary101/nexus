import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { AgentTask, AgentTaskList, AgentStep } from "../lib/types";
import { Card, Empty, ErrorNote, StatusBadge } from "../components/ui";
import { fmtDateTime } from "../lib/format";

const STEP_ICON: Record<AgentStep["type"], string> = {
  PLANNER: "◆",
  TOOL: "⚙",
  DATA: "▤",
  MODEL: "∿",
  LLM: "✦",
  REPORT: "✓",
  GATE: "⏸",
};

export default function AgentTracePage() {
  const [selected, setSelected] = useState<string | null>(null);
  const list = useQuery<AgentTaskList>({
    queryKey: ["agent-tasks-all"],
    queryFn: () => api<AgentTaskList>("/agent/tasks?limit=50"),
  });
  const detail = useQuery<AgentTask>(
    { queryKey: ["agent-task", selected], queryFn: () => api<AgentTask>(`/agent/tasks/${selected}`), enabled: !!selected },
  );

  const task: AgentTask | null = detail.data ?? (selected ? null : list.data?.items[0] ?? null);
  const tasks = list.data?.items ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Agent Trace</h1>
        <p className="mt-1 text-sm text-ink-faint">
          Every run is a sequence of declared tool calls with real arguments, results, timings
          and approval gates — nothing is simulated progress.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Runs">
          {tasks.length === 0 ? (
            <Empty title="No agent runs yet" hint="Run a request from the Command Center." />
          ) : (
            <ul className="space-y-2">
              {tasks.map((t) => (
                <li key={t.id}>
                  <button
                    onClick={() => setSelected(t.id)}
                    className={`w-full rounded-lg border p-3 text-left transition-colors ${
                      task?.id === t.id ? "border-accent/40 bg-accent/5" : "border-line bg-raised/30 hover:border-line/80"
                    }`}
                  >
                    <div className="line-clamp-2 text-sm text-ink">{t.request}</div>
                    <div className="mt-1.5 flex items-center justify-between">
                      <StatusBadge status={t.status} />
                      <span className="text-[11px] text-ink-faint">{fmtDateTime(t.created_at)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-4 lg:col-span-2">
          {!task ? (
            <Card>
              <Empty title="Select a run" hint="Pick a run on the left to inspect its execution steps." />
            </Card>
          ) : (
            <>
              <Card
                title={`Run · ${task.intent}`}
                action={
                  <div className="flex items-center gap-2">
                    <StatusBadge status={task.status} />
                    {task.finished_at && <span className="text-[11px] text-ink-faint">finished {fmtDateTime(task.finished_at)}</span>}
                  </div>
                }
              >
                <div className="rounded-lg border border-line bg-raised/40 px-4 py-3 text-sm text-ink-dim">“{task.request}”</div>
                {detail.isLoading && <div className="mt-3 text-xs text-ink-faint">Loading steps…</div>}
              </Card>

              <Card title="Execution steps">
                {detail.data && detail.data.steps.length > 0 ? (
                  <ol className="relative space-y-0">
                    {detail.data.steps.map((s, i) => (
                      <li key={s.seq} className="relative flex gap-4 pb-6 last:pb-0">
                        {i < detail.data!.steps.length - 1 && (
                          <span className="absolute left-[15px] top-8 h-full w-px bg-line" />
                        )}
                        <span
                          className={`z-10 grid h-8 w-8 shrink-0 place-items-center rounded-full border text-xs ${
                            s.status === "FAILED"
                              ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                              : s.status === "PENDING_APPROVAL"
                                ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                                : s.status === "SKIPPED"
                                  ? "border-line bg-raised text-ink-faint"
                                  : "border-accent/40 bg-accent/10 text-accent"
                          }`}
                        >
                          {STEP_ICON[s.type]}
                        </span>
                        <div className="min-w-0 flex-1 pt-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-sm text-ink">{s.name}</span>
                            <span className="rounded border border-line px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-ink-faint">
                              {s.type}
                            </span>
                            <StatusBadge status={s.status} />
                            {s.duration_ms > 0 && (
                              <span className="text-[11px] tabular-nums text-ink-faint">{Math.round(s.duration_ms)}ms</span>
                            )}
                          </div>
                          {s.detail && <div className="mt-1 text-xs text-ink-dim">{s.detail}</div>}
                          {(Object.keys(s.args).length > 0 || Object.keys(s.result).length > 0) && (
                            <details className="mt-2">
                              <summary className="cursor-pointer text-[11px] text-ink-faint hover:text-accent">
                                args / result
                              </summary>
                              <pre className="mt-1 max-h-56 overflow-auto rounded-lg border border-line bg-base/60 p-3 text-[11px] leading-relaxed text-ink-dim">
                                {JSON.stringify({ args: s.args, result: s.result }, null, 2)}
                              </pre>
                            </details>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <Empty title="No steps recorded yet" />
                )}
                {detail.data?.response_text && (
                  <div className="mt-4 rounded-lg border border-line bg-raised/40 p-4">
                    <div className="panel-title mb-2">Final response</div>
                    <div className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{detail.data.response_text}</div>
                  </div>
                )}
              </Card>
            </>
          )}
          {detail.isError && <ErrorNote message={String(detail.error)} />}
        </div>
      </div>
    </div>
  );
}
