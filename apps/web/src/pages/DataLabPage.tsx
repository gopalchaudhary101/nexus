import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";
import type { Anomaly, Forecast, Subscription, SpendingSeries } from "../lib/types";
import { Badge, Card, Empty, ErrorNote, Spinner, StatusBadge } from "../components/ui";
import { fmtDate, fmtMoney } from "../lib/format";

const TABS = ["Subscriptions", "Anomalies", "Forecast", "Spending"] as const;
type Tab = (typeof TABS)[number];

export default function DataLabPage() {
  const [tab, setTab] = useState<Tab>("Subscriptions");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Data Lab</h1>
        <p className="mt-1 text-sm text-ink-faint">
          Data-science features running on your data. Every card states its model, inputs and
          confidence — and says so plainly when there isn't enough data.
        </p>
      </header>
      <div className="flex gap-1.5">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-lg border px-4 py-1.5 text-sm ${tab === t ? "border-accent/50 bg-accent/10 text-accent" : "border-line text-ink-dim hover:text-ink"}`}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Subscriptions" && <SubscriptionsTab />}
      {tab === "Anomalies" && <AnomaliesTab />}
      {tab === "Forecast" && <ForecastTab />}
      {tab === "Spending" && <SpendingTab />}
    </div>
  );
}

function SubscriptionsTab() {
  const subs = useQuery<Subscription[]>({ queryKey: ["subscriptions"], queryFn: () => api<Subscription[]>("/insights/subscriptions") });
  if (subs.isLoading) return <Spinner />;
  if (subs.isError) return <ErrorNote message={String(subs.error)} />;
  const s = subs.data!;
  const monthly = s.reduce((a, b) => a + b.monthly_equivalent, 0);
  const annual = s.reduce((a, b) => a + b.annualized_cost, 0);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <Summary value={fmtMoney(monthly)} label="recurring / month" />
        <Summary value={fmtMoney(annual)} label="projected / year" />
        <Summary value={String(s.filter((x) => x.status === "ACTIVE").length)} label="active subscriptions" />
      </div>
      <Card>
        {s.length === 0 ? (
          <Empty
            title="No subscriptions detected yet"
            hint="Upload a transactions CSV — recurring merchants are detected from payment history (≥3 occurrences, interval regularity, amount stability). No usage claims are made."
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-ink-faint">
                <th className="pb-2 font-medium">Merchant</th>
                <th className="pb-2 font-medium">Frequency</th>
                <th className="pb-2 text-right font-medium">Amount</th>
                <th className="pb-2 text-right font-medium">≈ /year</th>
                <th className="pb-2 font-medium">Next due</th>
                <th className="pb-2 font-medium">Confidence</th>
                <th className="pb-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {s.map((x) => (
                <tr key={x.id}>
                  <td className="py-3 pr-2">
                    <div className="font-medium text-ink">{x.merchant}</div>
                    {x.price_increase && (
                      <div className="mt-0.5 text-[11px] text-amber-300">
                        ▲ price +{x.price_increase.pct}% on {fmtDate(x.price_increase.date)} (
                        {fmtMoney(x.price_increase.from)} → {fmtMoney(x.price_increase.to)})
                      </div>
                    )}
                    {x.notes.slice(0, 2).map((n, i) => (
                      <div key={i} className="mt-0.5 text-[11px] text-ink-faint">
                        {n}
                      </div>
                    ))}
                  </td>
                  <td className="py-3 text-ink-dim">{x.frequency.toLowerCase()}</td>
                  <td className="py-3 text-right tabular-nums">{fmtMoney(x.amount, x.currency)}</td>
                  <td className="py-3 text-right tabular-nums text-ink-dim">{fmtMoney(x.annualized_cost, x.currency)}</td>
                  <td className="py-3 text-ink-dim">{fmtDate(x.next_due)}</td>
                  <td className="py-3">
                    <Badge tone="neutral">{Math.round(x.confidence * 100)}%</Badge>
                  </td>
                  <td className="py-3">
                    <StatusBadge status={x.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <p className="text-xs leading-relaxed text-ink-faint">
        Detection: group payments by normalised merchant, require ≥3 occurrences, classify the
        median interval (weekly/monthly/quarterly/yearly) and score regularity + amount
        stability. “Lapsed” means no payment in &gt;2.5 cycles — it is never a claim that the
        service is unused.
      </p>
    </div>
  );
}

function AnomaliesTab() {
  const anoms = useQuery<Anomaly[]>({ queryKey: ["anomalies"], queryFn: () => api<Anomaly[]>("/insights/anomalies") });
  if (anoms.isLoading) return <Spinner />;
  if (anoms.isError) return <ErrorNote message={String(anoms.error)} />;
  const a = anoms.data!;
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-4 py-3 text-xs leading-relaxed text-amber-200">
        Anomaly ≠ fraud. These are statistical deviations from <em>your own</em> transaction
        pattern (model: {a[0]?.model ?? "isolation-forest-v1"}). Review recommended before any
        action.
      </div>
      <Card>
        {a.length === 0 ? (
          <Empty
            title="No anomaly run yet"
            hint="Needs ≥8 transactions. Import a transactions CSV, then ask the agent “Show unusual transactions” or run it from the Command Center."
          />
        ) : (
          <ul className="space-y-3">
            {a.map((x) => (
              <li key={x.transaction_id} className="rounded-lg border border-line bg-raised/40 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <Badge tone={x.label === "HIGHLY_UNUSUAL" ? "bad" : "warn"}>{x.label}</Badge>
                    <span className="font-medium text-ink">{x.description}</span>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="tabular-nums text-ink">{fmtMoney(x.amount, x.currency)}</span>
                    <span className="text-xs text-ink-faint">{fmtDate(x.date)}</span>
                    <Badge tone="neutral">score {x.score.toFixed(3)}</Badge>
                  </div>
                </div>
                {x.explanations.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {x.explanations.map((e, i) => (
                      <span key={i} className="rounded-md border border-line bg-base/50 px-2 py-1 text-[11px] text-ink-dim">
                        {e.why}
                        <span className="ml-1.5 text-ink-faint">z={e.z}</span>
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function ForecastTab() {
  const fc = useQuery<Forecast>({ queryKey: ["forecast"], queryFn: () => api<Forecast>("/insights/forecast") });
  if (fc.isLoading) return <Spinner />;
  if (fc.isError) return <ErrorNote message={String(fc.error)} />;
  const f = fc.data!;
  const chart = [
    ...f.history.map((h) => ({ month: h.month.slice(2), value: h.total, lo: null as number | null, hi: null as number | null, kind: "history" })),
    ...f.points.map((p) => ({ month: p.month.slice(2), value: p.value, lo: p.lo, hi: p.hi, kind: "forecast" })),
  ];
  const lastHist = f.history.length ? f.history[f.history.length - 1].month.slice(2) : null;
  return (
    <div className="space-y-4">
      <Card
        title={`Monthly spending forecast · ${f.model}`}
        action={f.trend_pct_mom !== null ? <Badge tone={f.trend_pct_mom > 0 ? "warn" : "good"}>{f.trend_pct_mom > 0 ? "▲" : "▼"} {Math.abs(f.trend_pct_mom)}% MoM</Badge> : undefined}
      >
        <div className="mb-3 rounded-lg border border-line bg-raised/40 px-4 py-2.5 text-xs leading-relaxed text-ink-dim">
          {f.message}
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chart} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <defs>
              <linearGradient id="hist" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1e2a3d" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="month" tick={{ fill: "#5b6c85", fontSize: 11 }} stroke="#1e2a3d" />
            <YAxis tick={{ fill: "#5b6c85", fontSize: 11 }} stroke="#1e2a3d" width={64} />
            <Tooltip
              contentStyle={{ background: "#151f30", border: "1px solid #1e2a3d", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#e2e8f0" }}
              formatter={(v: number | string, name: string) => [Number(v).toLocaleString("en-IN"), name]}
            />
            {lastHist && <ReferenceLine x={lastHist} stroke="#5b6c85" strokeDasharray="4 4" />}
            <Area type="monotone" dataKey="hi" name="95% upper" stroke="none" fill="url(#band)" connectNulls />
            <Area type="monotone" dataKey="lo" name="95% lower" stroke="none" fill="#101724" connectNulls />
            <Area type="monotone" dataKey="value" name="Spending" stroke="#22d3ee" strokeWidth={2} fill="url(#hist)" connectNulls />
          </AreaChart>
        </ResponsiveContainer>
        <div className="mt-2 flex gap-4 text-[11px] text-ink-faint">
          <span><span className="mr-1 inline-block h-2 w-3 rounded-sm bg-accent/70" />actual</span>
          <span><span className="mr-1 inline-block h-2 w-3 rounded-sm bg-violet-glow/50" />95% forecast band</span>
        </div>
      </Card>
    </div>
  );
}

function SpendingTab() {
  const sp = useQuery<SpendingSeries>({ queryKey: ["spending"], queryFn: () => api<SpendingSeries>("/analytics/spending") });
  if (sp.isLoading) return <Spinner />;
  if (sp.isError) return <ErrorNote message={String(sp.error)} />;
  const s = sp.data!;
  if (s.months.every((m) => m.total === 0))
    return (
      <Card>
        <Empty title="No spending history yet" hint="Import a transactions CSV to see the monthly breakdown (recurring vs other)." />
      </Card>
    );
  return (
    <Card title={`Monthly spending (${s.currency})`}>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={s.months} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="#1e2a3d" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="month" tick={{ fill: "#5b6c85", fontSize: 11 }} stroke="#1e2a3d" />
          <YAxis tick={{ fill: "#5b6c85", fontSize: 11 }} stroke="#1e2a3d" width={64} />
          <Tooltip
            contentStyle={{ background: "#151f30", border: "1px solid #1e2a3d", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#e2e8f0" }}
            formatter={(v: number | string, name: string) => [Number(v).toLocaleString("en-IN"), name]}
          />
          <Line type="monotone" dataKey="total" name="Total" stroke="#22d3ee" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="recurring" name="Recurring" stroke="#8b5cf6" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="other" name="Other" stroke="#34d399" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}

function Summary({ value, label }: { value: string; label: string }) {
  return (
    <div className="panel p-4">
      <div className="text-2xl font-semibold tracking-tight text-ink">{value}</div>
      <div className="mt-1 text-xs text-ink-faint">{label}</div>
    </div>
  );
}
