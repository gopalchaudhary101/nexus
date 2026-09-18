import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Deadline, Overview, Subscription } from "../lib/types";
import { Card, Empty, RiskBadge, Spinner, StatusBadge, ErrorNote } from "../components/ui";
import { fmtDate, fmtMoney } from "../lib/format";

export default function DashboardPage() {
  const ov = useQuery<Overview>({ queryKey: ["overview"], queryFn: () => api<Overview>("/insights/overview") });
  const deadlines = useQuery<Deadline[]>({ queryKey: ["deadlines"], queryFn: () => api<Deadline[]>("/insights/deadlines") });
  const subs = useQuery<Subscription[]>({ queryKey: ["subscriptions"], queryFn: () => api<Subscription[]>("/insights/subscriptions") });

  if (ov.isError) return <ErrorNote message={String(ov.error)} />;
  if (ov.isLoading) return <Spinner label="Loading your overview…" />;

  const o = ov.data!;
  const dl = deadlines.data ?? [];
  const s = subs.data ?? [];
  const nextBillings = s
    .filter((x) => x.status === "ACTIVE")
    .sort((a, b) => a.next_due.localeCompare(b.next_due))
    .slice(0, 4);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Command Overview</h1>
          <p className="mt-1 text-sm text-ink-faint">
            What needs your attention — derived from your documents, transactions and messages.
          </p>
        </div>
        <Link to="/agents" className="btn btn-primary">
          Ask NEXUS →
        </Link>
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Needs attention" value={o.needs_attention} tone={o.needs_attention > 0 ? "bad" : "good"} to="/approvals" />
        <StatCard label="Upcoming (30d)" value={o.upcoming} sub="deadlines" to="/datalab" />
        <StatCard label="Risk signals" value={o.risk_signals} tone={o.risk_signals > 0 ? "warn" : "neutral"} to="/risk" />
        <StatCard
          label="Recurring / month"
          value={fmtMoney(o.recurring_monthly, o.recurring_currency)}
          sub={`${o.ready_documents}/${o.documents} documents indexed`}
          to="/datalab"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Priority feed" className="lg:col-span-2">
          {o.recent.length === 0 ? (
            <Empty
              title="Nothing urgent right now"
              hint="Upload documents or a transactions CSV in Documents — NEXUS will derive deadlines, subscriptions and risk signals from them."
            />
          ) : (
            <ul className="divide-y divide-line">
              {o.recent.map((item) => (
                <li key={`${item.kind}-${item.ref}`} className="flex items-start gap-3 py-3">
                  <span
                    className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                      item.severity === "HIGH" || item.severity === "RISK"
                        ? "bg-rose-400"
                        : item.severity === "MEDIUM"
                          ? "bg-amber-400"
                          : "bg-line"
                    }`}
                  />
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-ink">{item.title}</div>
                    <div className="mt-0.5 text-xs text-ink-faint">{item.detail}</div>
                  </div>
                  <span className="ml-auto shrink-0 text-[10px] uppercase tracking-wider text-ink-faint">
                    {item.kind}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Deadlines" action={<Link to="/datalab" className="text-xs text-accent hover:underline">Data Lab →</Link>}>
          {dl.length === 0 ? (
            <Empty title="No deadlines detected" hint="Deadlines are extracted from bills, policies, contracts and offers with page-level source references." />
          ) : (
            <ul className="space-y-3">
              {dl.slice(0, 6).map((d) => (
                <li key={d.id} className="rounded-lg border border-line bg-raised/40 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">{d.title}</span>
                    <RiskBadge level={d.risk_level} />
                  </div>
                  <div className="mt-1 flex items-center justify-between text-xs text-ink-faint">
                    <span>
                      {fmtDate(d.due_date)} · {d.days_remaining}d
                    </span>
                    {d.amount ? <span className="tabular-nums text-ink-dim">{fmtMoney(d.amount, d.currency)}</span> : null}
                  </div>
                  {d.source_ref && <div className="mt-1 truncate text-[11px] text-ink-faint">src: {d.source_ref}</div>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Next subscription billings">
          {nextBillings.length === 0 ? (
            <Empty title="No active subscriptions detected" hint="Upload a transactions CSV — recurring merchants are detected from payment history." />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-ink-faint">
                  <th className="pb-2 font-medium">Merchant</th>
                  <th className="pb-2 font-medium">Next due</th>
                  <th className="pb-2 text-right font-medium">Amount</th>
                  <th className="pb-2 text-right font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {nextBillings.map((x) => (
                  <tr key={x.id}>
                    <td className="py-2.5 pr-2">
                      <div className="font-medium text-ink">{x.merchant}</div>
                      <div className="text-[11px] text-ink-faint">{x.frequency.toLowerCase()} · conf {Math.round(x.confidence * 100)}%</div>
                    </td>
                    <td className="py-2.5 text-ink-dim">{fmtDate(x.next_due)}</td>
                    <td className="py-2.5 text-right tabular-nums">{fmtMoney(x.amount, x.currency)}</td>
                    <td className="py-2.5 text-right">
                      <StatusBadge status={x.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Knowledge coverage" className="flex flex-col">
          <div className="flex items-center gap-4">
            <div className="relative grid h-20 w-20 place-items-center">
              <svg viewBox="0 0 36 36" className="h-20 w-20 -rotate-90">
                <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1e2a3d" strokeWidth="3" />
                <circle
                  cx="18"
                  cy="18"
                  r="15.9"
                  fill="none"
                  stroke="#22d3ee"
                  strokeWidth="3"
                  strokeDasharray={`${o.knowledge_coverage * 100} 100`}
                  strokeLinecap="round"
                />
              </svg>
              <span className="absolute text-sm font-semibold">{Math.round(o.knowledge_coverage * 100)}%</span>
            </div>
            <div className="text-sm text-ink-dim">
              of the 13 document categories are represented in your vault.
              <div className="mt-2 text-xs text-ink-faint">
                The personal knowledge graph links documents → merchants → deadlines → risks.
              </div>
              <Link to="/graph" className="mt-2 inline-block text-xs text-accent hover:underline">
                Open graph →
              </Link>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  tone = "neutral",
  to,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  tone?: "neutral" | "bad" | "warn" | "good";
  to: string;
}) {
  const color =
    tone === "bad" ? "text-rose-300" : tone === "warn" ? "text-amber-300" : tone === "good" ? "text-emerald-300" : "text-ink";
  return (
    <Link to={to} className="panel block p-4 transition-colors hover:border-accent/30">
      <div className="panel-title">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tracking-tight ${color}`}>{value}</div>
      {sub ? <div className="mt-1 text-xs text-ink-faint">{sub}</div> : null}
    </Link>
  );
}
