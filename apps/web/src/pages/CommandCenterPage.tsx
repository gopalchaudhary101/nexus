import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, runAgentSSE, AgentSSEEvent } from "../lib/api";
import type { AgentTask } from "../lib/types";
import { Card, ErrorNote } from "../components/ui";
import { fmtDateTime } from "../lib/format";

const CHIPS = [
  "What needs my attention this week?",
  "What is expiring soon?",
  "Review my subscriptions and recurring spend",
  "Show unusual transactions",
  "Forecast my spending",
];

interface LiveStep {
  kind: "planner" | "tool" | "gate" | "final";
  text: string;
  tone?: "ok" | "warn" | "bad";
  ts: number;
}

export default function CommandCenterPage() {
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<LiveStep[]>([]);
  const [response, setResponse] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const client = useQueryClient();

  const history = useQuery<AgentTask[]>({
    queryKey: ["agent-tasks"],
    queryFn: () => api<{ items: AgentTask[]; total: number }>("/agent/tasks?limit=6").then((r) => r.items),
  });

  const run = async (text: string) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    setResponse(null);
    setLive([]);
    setLastRun(null);
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await runAgentSSE(
        text,
        (evt: AgentSSEEvent) => {
          const ts = Date.now();
          if (evt.type === "planner") {
            setLive((l) => [...l, { kind: "planner", text: `Intent: ${evt.intent} → ${evt.steps.join(" → ")}`, ts }]);
          } else if (evt.type === "tool") {
            setLive((l) => [
              ...l,
              { kind: "tool", text: `${evt.tool}: ${evt.summary}`, tone: evt.status === "OK" ? "ok" : "bad", ts },
            ]);
          } else if (evt.type === "gate") {
            setLive((l) => [
              ...l,
              {
                kind: "gate",
                text: `Approval required: ${evt.tool} [${evt.risk_class}] — decide in Approvals`,
                tone: "warn",
                ts,
              },
            ]);
          } else if (evt.type === "final") {
            setResponse(evt.response);
          } else if (evt.type === "done") {
            setLastRun(evt.run_id);
          }
        },
        ac.signal,
      );
      client.invalidateQueries();
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Command Center</h1>
        <p className="mt-1 text-sm text-ink-faint">
          NEXUS observes → retrieves evidence → analyzes → explains → proposes. Consequential
          actions pause for your approval.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <textarea
              className="input min-h-[88px] resize-y"
              placeholder='e.g. "What needs my attention this week?"'
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run(request);
              }}
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button className="btn btn-primary" disabled={busy || !request.trim()} onClick={() => run(request)}>
                {busy ? "Running…" : "Run agent"}
              </button>
              {busy && (
                <button
                  className="btn"
                  onClick={() => {
                    abortRef.current?.abort();
                    setBusy(false);
                  }}
                >
                  Cancel stream
                </button>
              )}
              <span className="ml-auto text-xs text-ink-faint">⌘/Ctrl + Enter to run</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {CHIPS.map((c) => (
                <button
                  key={c}
                  disabled={busy}
                  onClick={() => {
                    setRequest(c);
                    run(c);
                  }}
                  className="rounded-full border border-line bg-raised/50 px-3 py-1 text-xs text-ink-dim transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40"
                >
                  {c}
                </button>
              ))}
            </div>
          </Card>

          {live.length > 0 && (
            <Card title="Live execution" className="font-mono">
              <ol className="space-y-1.5 text-xs">
                {live.map((s, i) => (
                  <li key={i} className="flex gap-2">
                    <span
                      className={
                        s.tone === "bad" ? "text-rose-400" : s.tone === "warn" ? "text-amber-300" : s.tone === "ok" ? "text-emerald-300" : "text-accent"
                      }
                    >
                      {s.kind === "planner" ? "◆" : s.kind === "gate" ? "⏸" : s.kind === "final" ? "✓" : "·"}
                    </span>
                    <span className="text-ink-dim">{s.text}</span>
                  </li>
                ))}
                {busy && <li className="flex gap-2 text-ink-faint"><span className="animate-pulseSoft">·</span> waiting for next event…</li>}
              </ol>
            </Card>
          )}

          {response && (
            <Card
              title="Response"
              action={
                lastRun ? (
                  <Link to="/trace" className="text-xs text-accent hover:underline">
                    View full trace →
                  </Link>
                ) : undefined
              }
            >
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{response}</div>
            </Card>
          )}
          {error && <ErrorNote message={error} />}
        </div>

        <Card title="Recent runs">
          {history.data && history.data.length === 0 ? (
            <div className="text-sm text-ink-faint">No runs yet — ask something above.</div>
          ) : (
            <ul className="space-y-3">
              {(history.data ?? []).map((t) => (
                <li key={t.id} className="rounded-lg border border-line bg-raised/40 p-3">
                  <div className="line-clamp-2 text-sm text-ink">{t.request}</div>
                  <div className="mt-1.5 flex items-center justify-between text-[11px] text-ink-faint">
                    <span>
                      {t.intent} · {t.steps.length} steps
                    </span>
                    <span>{fmtDateTime(t.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
