import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, registerSchema, loginSchema, setToken, ApiError } from "../lib/api";
import type { AuthResponse } from "../lib/types";

export default function LandingPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("demo@nexus.dev");
  const [password, setPassword] = useState("nexus-demo-2026");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const parsed = mode === "register" ? registerSchema.safeParse({ email, password, name }) : loginSchema.safeParse({ email, password });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid input");
      return;
    }
    setBusy(true);
    try {
      const data = await api<AuthResponse>(
        mode === "register" ? "/auth/register" : "/auth/login",
        { method: "POST", body: parsed.data },
      );
      setToken(data.access_token);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full">
      {/* left: product story */}
      <div className="relative hidden flex-1 flex-col justify-between overflow-hidden border-r border-line p-12 lg:flex">
        <div className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-violet-glow/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 right-0 h-96 w-96 rounded-full bg-accent/10 blur-3xl" />
        <div>
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-accent/80 to-violet-glow/80 text-base font-bold text-base">
              N
            </span>
            <div>
              <div className="text-base font-semibold tracking-[0.22em]">NEXUS</div>
              <div className="text-[10px] uppercase tracking-[0.26em] text-ink-faint">
                Personal Life Intelligence &amp; Action OS
              </div>
            </div>
          </div>
          <h1 className="mt-14 max-w-lg text-4xl font-semibold leading-tight tracking-tight text-ink">
            Your documents, bills and subscriptions —
            <span className="bg-gradient-to-r from-accent to-violet-300 bg-clip-text text-transparent">
              {" "}understood, explained, and actionable.
            </span>
          </h1>
          <ul className="mt-10 space-y-4 text-sm text-ink-dim">
            {[
              ["Grounded answers", "Every answer cites its source document and page — or NEXUS says it doesn't know."],
              ["Real data science", "Anomaly detection, subscription intelligence and forecasts run on your actual data, with explicit insufficient-data messages."],
              ["Safe agentic workflows", "Read-only tools run freely; anything consequential asks for your approval first — with a full audit trail."],
            ].map(([t, d]) => (
              <li key={t} className="flex gap-3">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                <div>
                  <div className="font-medium text-ink">{t}</div>
                  <div className="text-ink-faint">{d}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="max-w-md text-xs leading-relaxed text-ink-faint">
          NEXUS is decision support, not a legal, medical or financial advisor.
          It never labels anomalies as fraud, and it never claims a subscription
          is unused without usage evidence.
        </p>
      </div>

      {/* right: auth form */}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <div className="panel p-7">
            <div className="mb-6 grid grid-cols-2 rounded-lg border border-line bg-raised/50 p-1 text-sm">
              {(["login", "register"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    setMode(m);
                    setError(null);
                  }}
                  className={`rounded-md py-1.5 font-medium transition-colors ${
                    mode === m ? "bg-accent/15 text-accent" : "text-ink-dim hover:text-ink"
                  }`}
                >
                  {m === "login" ? "Sign in" : "Create account"}
                </button>
              ))}
            </div>
            <form onSubmit={submit} className="space-y-4">
              {mode === "register" && (
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-ink-dim">Name</label>
                  <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
                </div>
              )}
              <div>
                <label className="mb-1.5 block text-xs font-medium text-ink-dim">Email</label>
                <input
                  className="input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-ink-dim">Password</label>
                <input
                  className="input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={8}
                  required
                />
              </div>
              {error && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
                  {error}
                </div>
              )}
              <button className="btn btn-primary w-full justify-center" disabled={busy}>
                {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
              </button>
            </form>
          </div>
          <div className="mt-4 rounded-lg border border-line bg-surface/60 px-4 py-3 text-xs text-ink-faint">
            <span className="font-medium text-ink-dim">Demo workspace:</span> pre-seeded with
            synthetic personal data. Login is pre-filled — the password is
            <code className="mx-1 rounded bg-raised px-1.5 py-0.5 font-mono text-[11px] text-ink-dim">
              nexus-demo-2026
            </code>
            (run <code className="font-mono text-[11px]">make demo</code> to seed).
          </div>
        </div>
      </div>
    </div>
  );
}
