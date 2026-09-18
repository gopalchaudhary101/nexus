import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { RiskAnalytics, RiskReport } from "../lib/types";
import { Badge, Card, Empty, ErrorNote, RiskBadge, Spinner } from "../components/ui";
import { fmtDateTime } from "../lib/format";

const SAMPLES: { label: string; text: string }[] = [
  {
    label: "Suspicious (bank scare)",
    text: "URGENT: Your bank account will be suspended within 24 hours. Verify your password and OTP at http://secure-bank-verify.co/login now or lose access forever. Do not share this with anyone.",
  },
  {
    label: "Suspicious (CEO fraud)",
    text: "This is your manager from the US office. I am travelling and cannot speak. I need an urgent bank transfer of $12,000 to a vendor today. Keep this secret and do not tell anyone until we speak. Call +1 555 0142 for account details.",
  },
  {
    label: "Normal (utility notice)",
    text: "Hi Demo, your utility bill for September has been generated. You can review your usage details and pay online from your account portal at any time before the due date shown in your account. Thanks, City Power.",
  },
];

export default function RiskCenterPage() {
  const [text, setText] = useState(SAMPLES[0].text);
  const [report, setReport] = useState<RiskReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const analytics = useQuery<RiskAnalytics>({ queryKey: ["risk-analytics"], queryFn: () => api<RiskAnalytics>("/analytics/risk") });

  const analyze = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setReport(await api<RiskReport>("/risk/analyze", { body: { text } }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Risk Center</h1>
        <p className="mt-1 text-sm text-ink-faint">
          Multi-signal scam/risk engine: named heuristics (urgency, threats, payment/credential
          requests, secrecy, impersonation, link analysis) fused with a Naive Bayes classifier
          trained on a synthetic labeled corpus. Output is a risk assessment — never a fraud
          verdict.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Analyze a message">
          <div className="mb-3 flex flex-wrap gap-2">
            {SAMPLES.map((s) => (
              <button
                key={s.label}
                onClick={() => setText(s.text)}
                className="rounded-full border border-line bg-raised/50 px-3 py-1 text-xs text-ink-dim hover:border-accent/40 hover:text-accent"
              >
                {s.label}
              </button>
            ))}
          </div>
          <textarea className="input min-h-[140px] resize-y font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="mt-3 flex items-center gap-3">
            <button className="btn btn-primary" disabled={busy} onClick={analyze}>
              {busy ? "Analyzing…" : "Analyze"}
            </button>
            {error && <span className="text-xs text-rose-300">{error}</span>}
          </div>

          {report && (
            <div className="mt-5 space-y-3">
              <div
                className={`flex flex-wrap items-center gap-3 rounded-lg border p-4 ${
                  report.risk_level === "HIGH"
                    ? "border-rose-500/40 bg-rose-500/5"
                    : report.risk_level === "MEDIUM"
                      ? "border-amber-500/30 bg-amber-500/5"
                      : "border-emerald-500/30 bg-emerald-500/5"
                }`}
              >
                <RiskBadge level={report.risk_level} />
                <span className="text-lg font-semibold tabular-nums">score {report.score.toFixed(3)}</span>
                <div className="ml-auto flex gap-3 text-[11px] text-ink-faint">
                  <span>rules {String(report.components["rules"] ?? "—")}</span>
                  <span>classifier {String(report.components["classifier"] ?? "—")}</span>
                  <span>{String(report.components["fusion"] ?? "")}</span>
                </div>
              </div>
              {report.signals.length > 0 && (
                <div>
                  <div className="panel-title mb-2">Signals fired</div>
                  <ul className="space-y-2">
                    {report.signals.map((s, i) => (
                      <li key={i} className="rounded-lg border border-line bg-raised/30 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm text-ink">{s.label}</span>
                          <Badge tone="neutral">w {s.weight}</Badge>
                        </div>
                        {s.evidence && <div className="mt-1 truncate font-mono text-[11px] text-ink-faint">“{s.evidence}”</div>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="rounded-lg border border-line bg-base/50 px-4 py-3 text-xs leading-relaxed text-ink-faint">
                ⚖ {report.disclaimer}
              </div>
            </div>
          )}
        </Card>

        <div className="space-y-6">
          <Card title="Risk history">
            {!analytics.data ? (
              <Spinner />
            ) : analytics.data.total === 0 ? (
              <Empty title="No risks recorded yet" hint="Analyzed messages and agent risk checks are stored here." />
            ) : (
              <>
                <div className="mb-4 flex flex-wrap gap-2">
                  {Object.entries(analytics.data.by_level).map(([k, v]) => (
                    <Badge key={k} tone={k === "HIGH" || k === "CRITICAL" ? "bad" : k === "MEDIUM" ? "warn" : "good"}>
                      {k} · {v}
                    </Badge>
                  ))}
                </div>
                <ul className="divide-y divide-line">
                  {analytics.data.recent.map((r) => (
                    <li key={r.id} className="flex items-center gap-3 py-2.5">
                      <RiskBadge level={r.level} />
                      <span className="min-w-0 flex-1 truncate text-sm text-ink-dim">{r.subject}</span>
                      <span className="text-xs tabular-nums text-ink-faint">{r.score.toFixed(2)}</span>
                      <span className="text-[11px] text-ink-faint">{fmtDateTime(r.created_at)}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {analytics.isError && <ErrorNote message={String(analytics.error)} />}
          </Card>

          {analytics.data && analytics.data.top_signals.length > 0 && (
            <Card title="Top signals">
              <ul className="space-y-2">
                {analytics.data.top_signals.map((s) => (
                  <li key={s.label} className="flex items-center gap-3">
                    <span className="w-64 truncate text-xs text-ink-dim">{s.label}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-accent to-violet-glow"
                        style={{ width: `${(s.count / Math.max(1, analytics.data!.top_signals[0].count)) * 100}%` }}
                      />
                    </div>
                    <span className="w-8 text-right text-xs tabular-nums text-ink-faint">{s.count}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
