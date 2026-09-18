import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, clearToken } from "../lib/api";
import type { HealthInfo, User } from "../lib/types";

const NAV = [
  { to: "/", label: "Dashboard", icon: "◧" },
  { to: "/agents", label: "Command Center", icon: "⌘" },
  { to: "/trace", label: "Agent Trace", icon: "⎇" },
  { to: "/documents", label: "Documents", icon: "▤" },
  { to: "/graph", label: "Knowledge Graph", icon: "◉" },
  { to: "/datalab", label: "Data Lab", icon: "∿" },
  { to: "/rag-eval", label: "RAG & Eval", icon: "❝" },
  { to: "/approvals", label: "Approvals", icon: "✓" },
  { to: "/risk", label: "Risk Center", icon: "⚠" },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState<User | null>(null);

  const { data: health } = useQuery<HealthInfo>({
    queryKey: ["health"],
    queryFn: () => api<HealthInfo>("/health"),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => {
        clearToken();
        navigate("/login");
      });
  }, [navigate]);

  const logout = () => {
    clearToken();
    navigate("/login");
  };

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-surface/60">
        <Link to="/" className="flex items-center gap-2.5 px-5 pb-5 pt-6">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-accent/80 to-violet-glow/80 text-sm font-bold text-base">
            N
          </span>
          <div>
            <div className="text-sm font-semibold tracking-[0.18em] text-ink">NEXUS</div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-ink-faint">Life OS</div>
          </div>
        </Link>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-accent/10 text-accent"
                    : "text-ink-dim hover:bg-raised/60 hover:text-ink"
                }`
              }
            >
              <span className="w-4 text-center opacity-80">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-line p-4">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-ink">{user?.name ?? "…"}</div>
              <div className="truncate text-xs text-ink-faint">{user?.email}</div>
            </div>
            <button
              onClick={logout}
              className="rounded-md border border-line px-2.5 py-1 text-xs text-ink-dim hover:border-rose-500/40 hover:text-rose-300"
            >
              Sign out
            </button>
          </div>
          {health && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="rounded border border-line bg-raised/50 px-1.5 py-0.5 text-[10px] text-ink-faint">
                api v{health.version}
              </span>
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] ${
                  health.llm_provider === "mock"
                    ? "border-amber-500/30 bg-amber-500/5 text-amber-300"
                    : "border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
                }`}
              >
                LLM: {health.llm_provider}
              </span>
              <span className="rounded border border-line bg-raised/50 px-1.5 py-0.5 text-[10px] text-ink-faint">
                embed: {health.embed_provider}
              </span>
            </div>
          )}
        </div>
      </aside>

      <main className="relative flex-1 overflow-y-auto">
        <div key={location.pathname} className="mx-auto max-w-6xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
