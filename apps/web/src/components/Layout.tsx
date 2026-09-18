import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, clearToken } from "../lib/api";
import type { HealthInfo, Notification, User } from "../lib/types";
import { timeAgo } from "../lib/format";
import { Empty } from "./ui";

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

function NotificationBell() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const notifs = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: () => api<Notification[]>("/notifications?limit=30"),
    refetchInterval: 30_000,
  });

  const markRead = useMutation({
    mutationFn: (id: string) => api<void>(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const markAllRead = useMutation({
    mutationFn: () => api<void>("/notifications/read-all", { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }),
  });

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const list = notifs.data ?? [];
  const unread = list.filter((n) => !n.read).length;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-lg border border-line bg-raised px-2.5 py-2 text-sm text-ink-dim transition-colors hover:border-accent/40 hover:text-ink"
        aria-label="Notifications"
      >
        🔔
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 w-80 rounded-xl border border-line bg-surface shadow-panel">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="panel-title">Notifications</span>
            {unread > 0 && (
              <button
                onClick={() => markAllRead.mutate()}
                disabled={markAllRead.isPending}
                className="text-xs text-accent hover:underline disabled:opacity-50"
              >
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto p-2">
            {list.length === 0 ? (
              <div className="p-3">
                <Empty title="No notifications" hint="Processing updates, deadlines and risk alerts will show up here." />
              </div>
            ) : (
              <ul className="space-y-1">
                {list.map((n) => (
                  <li key={n.id}>
                    <button
                      onClick={() => !n.read && markRead.mutate(n.id)}
                      className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${
                        n.read ? "opacity-60 hover:bg-raised/40" : "bg-accent/5 hover:bg-accent/10"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium text-ink">{n.title}</span>
                        {!n.read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />}
                      </div>
                      {n.body && <div className="mt-0.5 line-clamp-2 text-xs text-ink-faint">{n.body}</div>}
                      <div className="mt-1 text-[10px] uppercase tracking-wide text-ink-faint">
                        {n.kind} · {timeAgo(n.created_at)}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

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
          <Link to="/privacy" className="mt-3 block text-xs text-ink-faint hover:text-ink-dim hover:underline">
            Privacy &amp; data →
          </Link>
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
        <div className="flex justify-end border-b border-line/60 px-8 py-3">
          <NotificationBell />
        </div>
        <div key={location.pathname} className="mx-auto max-w-6xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
