import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { Approval } from "../lib/types";
import { Badge, Card, Empty, ErrorNote, StatusBadge } from "../components/ui";
import { fmtDateTime } from "../lib/format";

export default function ApprovalsPage() {
  const client = useQueryClient();
  const approvals = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => api<Approval[]>("/approvals"),
    refetchInterval: 4000,
  });
  const decide = useMutation({
    mutationFn: (a: { id: string; ok: boolean }) =>
      api<Approval>(`/approvals/${a.id}/${a.ok ? "approve" : "reject"}`, { method: "POST" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["approvals"] });
      client.invalidateQueries({ queryKey: ["agent-tasks"] });
      client.invalidateQueries({ queryKey: ["agent-tasks-all"] });
    },
  });

  const list = approvals.data ?? [];
  const pending = list.filter((a) => a.status === "PENDING");
  const history = list.filter((a) => a.status !== "PENDING");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Approvals</h1>
        <p className="mt-1 text-sm text-ink-faint">
          Default action policy: read-only tools run freely; SENSITIVE and CONSEQUENTIAL actions
          pause here until you explicitly approve or reject. Every decision is audit-logged.
        </p>
      </header>

      <Card title={`Pending (${pending.length})`}>
        {pending.length === 0 ? (
          <Empty
            title="No approvals waiting"
            hint="When the agent wants to create a reminder, send an email or modify anything, it will stop and ask here."
          />
        ) : (
          <ul className="space-y-3">
            {pending.map((a) => (
              <li key={a.id} className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge tone="warn">{a.risk_class}</Badge>
                  <span className="font-mono text-sm text-ink">{a.tool}</span>
                  {a.run_id && (
                    <Link to="/trace" className="text-xs text-accent hover:underline">
                      view run trace →
                    </Link>
                  )}
                  <span className="ml-auto text-[11px] text-ink-faint">{fmtDateTime(a.created_at)}</span>
                </div>
                <pre className="mt-3 max-h-40 overflow-auto rounded-lg border border-line bg-base/60 p-3 text-[11px] leading-relaxed text-ink-dim">
                  {JSON.stringify(a.args, null, 2)}
                </pre>
                <div className="mt-3 flex gap-2">
                  <button
                    className="btn btn-primary"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ id: a.id, ok: true })}
                  >
                    ✓ Approve &amp; execute
                  </button>
                  <button className="btn btn-danger" disabled={decide.isPending} onClick={() => decide.mutate({ id: a.id, ok: false })}>
                    ✕ Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {decide.isError && <div className="mt-3"><ErrorNote message={String(decide.error)} /></div>}
      </Card>

      <Card title="Decision history">
        {history.length === 0 ? (
          <div className="text-sm text-ink-faint">No decisions yet.</div>
        ) : (
          <ul className="divide-y divide-line">
            {history.slice(0, 20).map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 py-3">
                <StatusBadge status={a.status} />
                <span className="font-mono text-sm text-ink">{a.tool}</span>
                <span className="text-xs text-ink-faint">{fmtDateTime(a.created_at)}</span>
                {a.decided_at && <span className="text-xs text-ink-faint">decided {fmtDateTime(a.decided_at)}</span>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
