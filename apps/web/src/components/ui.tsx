import { ReactNode } from "react";

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel p-5 ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between">
          {title ? <h2 className="panel-title">{title}</h2> : <span />}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

const TONES: Record<string, string> = {
  neutral: "bg-line/60 text-ink-dim border-line",
  accent: "bg-accent/10 text-accent border-accent/30",
  good: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  warn: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  bad: "bg-rose-500/10 text-rose-300 border-rose-500/30",
  violet: "bg-violet-glow/10 text-violet-300 border-violet-glow/30",
};

export function Badge({
  tone = "neutral",
  children,
  pulse = false,
}: {
  tone?: keyof typeof TONES;
  children: ReactNode;
  pulse?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium tracking-wide ${TONES[tone]} ${
        pulse ? "animate-pulseSoft" : ""
      }`}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { tone: keyof typeof TONES; label: string }> = {
    UPLOADED: { tone: "neutral", label: "Queued" },
    PROCESSING: { tone: "warn", label: "Processing" },
    INDEXING: { tone: "warn", label: "Indexing" },
    READY: { tone: "good", label: "Ready" },
    FAILED: { tone: "bad", label: "Failed" },
    PENDING: { tone: "neutral", label: "Pending" },
    RUNNING: { tone: "accent", label: "Running" },
    WAITING_APPROVAL: { tone: "warn", label: "Awaiting approval" },
    COMPLETED: { tone: "good", label: "Completed" },
    OK: { tone: "good", label: "OK" },
    SKIPPED: { tone: "neutral", label: "Skipped" },
    PENDING_APPROVAL: { tone: "warn", label: "Needs approval" },
    EXECUTED: { tone: "good", label: "Executed" },
    REJECTED: { tone: "bad", label: "Rejected" },
    ACTIVE: { tone: "good", label: "Active" },
    LAPSED: { tone: "warn", label: "Lapsed" },
  };
  const m = map[status] ?? { tone: "neutral" as const, label: status };
  return (
    <Badge tone={m.tone} pulse={status === "PROCESSING" || status === "INDEXING" || status === "RUNNING"}>
      {m.label}
    </Badge>
  );
}

export function RiskBadge({ level }: { level: string }) {
  const tone =
    level === "CRITICAL" || level === "HIGH" ? "bad" : level === "MEDIUM" ? "warn" : "good";
  return <Badge tone={tone}>{level}</Badge>;
}

export function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: "neutral" | "accent" | "warn" | "bad" | "good";
}) {
  const color =
    tone === "accent" ? "text-accent" : tone === "warn" ? "text-amber-300" : tone === "bad" ? "text-rose-300" : tone === "good" ? "text-emerald-300" : "text-ink";
  return (
    <div className="panel p-4">
      <div className="panel-title">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tracking-tight ${color}`}>{value}</div>
      {sub ? <div className="mt-1 text-xs text-ink-faint">{sub}</div> : null}
    </div>
  );
}

export function ConfidenceBar({ value }: { value: number }) {
  const v = Math.round(value * 100);
  const color = v >= 70 ? "bg-emerald-400" : v >= 40 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-line">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${v}%` }} />
      </div>
      <span className="text-xs tabular-nums text-ink-dim">{v}%</span>
    </div>
  );
}

export function Spinner({ label = "Working…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-ink-dim">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line px-6 py-10 text-center">
      <div className="text-sm font-medium text-ink-dim">{title}</div>
      {hint ? <div className="mt-1 max-w-sm text-xs text-ink-faint">{hint}</div> : null}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-4 py-3 text-sm text-rose-300">
      {message}
    </div>
  );
}
