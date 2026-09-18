import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { KnowledgeGraph, GraphNode } from "../lib/types";
import { Card, Empty, ErrorNote, Spinner } from "../components/ui";
import { layoutForceGraph } from "../lib/forceGraph";

const W = 900;
const H = 620;

const KIND_COLOR: Record<string, string> = {
  USER: "#22d3ee",
  DOCUMENT: "#8b5cf6",
  MERCHANT: "#34d399",
  PERSON: "#f472b6",
  EMAIL: "#60a5fa",
  URL: "#f59e0b",
  DOMAIN: "#fbbf24",
  ACCOUNT_REF: "#fb7185",
  DEADLINE: "#f87171",
  SUBSCRIPTION: "#34d399",
  RISK: "#ef4444",
};

export default function KnowledgeGraphPage() {
  const g = useQuery<KnowledgeGraph>({ queryKey: ["graph"], queryFn: () => api<KnowledgeGraph>("/insights/graph") });
  const [hover, setHover] = useState<GraphNode | null>(null);
  const [filter, setFilter] = useState<string>("ALL");

  const data = g.data;
  const kinds = useMemo(() => {
    const s = new Set<string>();
    data?.nodes.forEach((n) => s.add(n.kind));
    return Array.from(s).sort();
  }, [data]);

  const positions = useMemo(() => {
    if (!data) return [];
    const ids = data.nodes.map((n) => n.id);
    return layoutForceGraph(ids, data.edges, W, H);
  }, [data]);

  const posById = useMemo(() => new Map(positions.map((p) => [p.id, p])), [positions]);
  const nodeById = useMemo(() => new Map(data?.nodes.map((n) => [n.id, n])), [data]);

  const visibleEdges = useMemo(() => {
    if (!data) return [];
    return data.edges.filter((e) => {
      const s = nodeById.get(e.src);
      const d = nodeById.get(e.dst);
      if (!s || !d) return false;
      if (filter === "ALL") return true;
      return s.kind === filter || d.kind === filter;
    });
  }, [data, filter, nodeById]);

  if (g.isLoading) return <Spinner label="Building graph…" />;
  if (g.isError) return <ErrorNote message={String(g.error)} />;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Personal Knowledge Graph</h1>
          <p className="mt-1 text-sm text-ink-faint">
            {data ? `${data.nodes.length} entities · ${data.edges.length} relationships` : ""} — stored
            relationally (Postgres in production); a dedicated graph DB is an optional extension.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setFilter("ALL")}
            className={`rounded-full border px-3 py-1 text-xs ${filter === "ALL" ? "border-accent/50 bg-accent/10 text-accent" : "border-line text-ink-dim hover:text-ink"}`}
          >
            All
          </button>
          {kinds.map((k) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${filter === k ? "border-accent/50 bg-accent/10 text-accent" : "border-line text-ink-dim hover:text-ink"}`}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: KIND_COLOR[k] ?? "#64748b" }} />
              {k}
            </button>
          ))}
        </div>
      </header>

      <Card>
        {!data || data.nodes.length === 0 ? (
          <Empty title="The graph is empty" hint="Upload documents — NEXUS links people, merchants, deadlines and risks as it reads them." />
        ) : (
          <div className="relative">
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Personal knowledge graph">
              <defs>
                <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="rgba(34,211,238,0.25)" />
                  <stop offset="100%" stopColor="rgba(34,211,238,0)" />
                </radialGradient>
              </defs>
              {visibleEdges.map((e, i) => {
                const s = posById.get(e.src);
                const d = posById.get(e.dst);
                if (!s || !d) return null;
                return (
                  <line
                    key={i}
                    x1={s.x}
                    y1={s.y}
                    x2={d.x}
                    y2={d.y}
                    stroke="#24344d"
                    strokeWidth={1}
                    opacity={0.7}
                  >
                    <title>{`${nodeById.get(e.src)?.name} --${e.rel}--> ${nodeById.get(e.dst)?.name}`}</title>
                  </line>
                );
              })}
              {data.nodes.map((n) => {
                const p = posById.get(n.id);
                if (!p) return null;
                const isUser = n.kind === "USER";
                const r = isUser ? 16 : n.kind === "DOCUMENT" ? 11 : n.kind === "DEADLINE" || n.kind === "RISK" ? 8 : 6;
                const dimmed = filter !== "ALL" && n.kind !== filter;
                return (
                  <g key={n.id} opacity={dimmed ? 0.25 : 1} onMouseEnter={() => setHover(n)} onMouseLeave={() => setHover(null)}>
                    {isUser && <circle cx={p.x} cy={p.y} r={r * 2.6} fill="url(#nodeGlow)" />}
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={r}
                      fill={KIND_COLOR[n.kind] ?? "#64748b"}
                      fillOpacity={0.85}
                      stroke="#0a0e14"
                      strokeWidth={2}
                    />
                    {(isUser || n.kind === "DOCUMENT" || hover?.id === n.id) && (
                      <text
                        x={p.x}
                        y={p.y - r - 6}
                        textAnchor="middle"
                        fontSize={10.5}
                        fill={hover?.id === n.id ? "#e2e8f0" : "#8fa3bd"}
                      >
                        {n.name.length > 34 ? `${n.name.slice(0, 32)}…` : n.name}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
            {hover && (
              <div className="pointer-events-none absolute left-4 top-4 max-w-xs rounded-lg border border-line bg-raised/95 p-3 shadow-panel">
                <div className="flex items-center gap-2 text-xs">
                  <span className="h-2 w-2 rounded-full" style={{ background: KIND_COLOR[hover.kind] ?? "#64748b" }} />
                  <span className="font-medium uppercase tracking-wider text-ink-faint">{hover.kind}</span>
                </div>
                <div className="mt-1 text-sm text-ink">{hover.name}</div>
                <pre className="mt-2 max-h-32 overflow-auto rounded bg-base/70 p-2 text-[10px] text-ink-dim">
                  {JSON.stringify(hover.attrs, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
