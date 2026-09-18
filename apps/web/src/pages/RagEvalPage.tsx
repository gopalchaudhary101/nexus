import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { AskResult, RagQuality, SearchHit } from "../lib/types";
import { Badge, Card, ConfidenceBar, Empty, ErrorNote, Spinner } from "../components/ui";

export default function RagEvalPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">RAG &amp; Evaluation</h1>
        <p className="mt-1 text-sm text-ink-faint">
          Ask grounded questions (with citations), and run the internal evaluation dataset
          against the live pipeline. Metrics are computed at runtime — never hardcoded.
        </p>
      </header>
      <div className="grid gap-6 lg:grid-cols-2">
        <AskCard />
        <EvalCard />
      </div>
    </div>
  );
}

function AskCard() {
  const [question, setQuestion] = useState("When does my insurance policy expire?");
  const [answer, setAnswer] = useState<AskResult | null>(null);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      const [a, s] = await Promise.all([
        api<AskResult>("/ask", { body: { question } }),
        api<{ hits: SearchHit[] }>("/search", { body: { query: question } }),
      ]);
      setAnswer(a);
      setHits(s.hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Ask (grounded Q&A)">
      <div className="flex gap-2">
        <input
          className="input flex-1"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="Ask about your documents…"
        />
        <button className="btn btn-primary" disabled={busy} onClick={run}>
          {busy ? "…" : "Ask"}
        </button>
      </div>
      {answer && (
        <div className="mt-4 space-y-3">
          <div
            className={`rounded-lg border p-4 text-sm leading-relaxed ${
              answer.grounded ? "border-line bg-raised/40 text-ink" : "border-amber-500/30 bg-amber-500/5 text-amber-200"
            }`}
          >
            {answer.answer}
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-ink-faint">Confidence</span>
              <ConfidenceBar value={answer.confidence} />
            </div>
            <Badge tone={answer.grounded ? "good" : "warn"}>{answer.grounded ? "Grounded in source" : "Not found in sources"}</Badge>
            <span className="text-[11px] text-ink-faint">provider: {answer.provider}</span>
          </div>
          {answer.sources.length > 0 && (
            <div>
              <div className="panel-title mb-1.5">Sources</div>
              <ul className="space-y-1">
                {answer.sources.map((s, i) => (
                  <li key={i} className="flex items-center justify-between rounded border border-line bg-base/50 px-3 py-1.5 text-xs">
                    <span className="font-mono text-ink-dim">{s.ref}</span>
                    <span className="tabular-nums text-ink-faint">sim {s.similarity}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {error && <div className="mt-3"><ErrorNote message={error} /></div>}
      <div className="mt-4">
        <div className="panel-title mb-1.5">Top retrievals</div>
        {hits.length === 0 ? (
          <div className="text-xs text-ink-faint">Run a question to see hybrid retrieval (vector + BM25) hits.</div>
        ) : (
          <ul className="space-y-1.5">
            {hits.map((h, i) => (
              <li key={h.chunk_id} className="rounded border border-line bg-raised/30 px-3 py-2">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-mono text-ink-dim">
                    {i + 1}. {h.document_name} · p{h.page}
                  </span>
                  <span className="tabular-nums text-ink-faint">
                    vec {h.vector_score} · bm25 {h.bm25_score} · <span className="text-accent">{h.score}</span>
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-ink-faint">{h.text}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function EvalCard() {
  const client = useQueryClient();
  const evalQ = useQuery<RagQuality>({
    queryKey: ["rag-quality"],
    queryFn: () => api<RagQuality>("/analytics/rag-quality"),
  });
  const runEval = useMutation({
    mutationFn: () => api<RagQuality>("/analytics/rag-quality/run", { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["rag-quality"] }),
  });

  const q = evalQ.data;
  return (
    <Card
      title="Internal RAG evaluation"
      action={
        <button className="btn btn-primary !py-1.5 text-xs" disabled={runEval.isPending} onClick={() => runEval.mutate()}>
          {runEval.isPending ? "Evaluating…" : "▶ Run evaluation"}
        </button>
      }
    >
      {runEval.isError && <div className="mb-3"><ErrorNote message={String(runEval.error)} /></div>}
      {!q ? (
        <Spinner />
      ) : !q.evaluated || !q.metrics ? (
        <Empty title="Not yet evaluated" hint={q.message ?? "Run the evaluation against the current document set."} />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Metric label="Precision @1" v={q.metrics.retrieval_precision_at_1} />
            <Metric label="Recall @5" v={q.metrics.retrieval_recall_at_5} />
            <Metric label="Citations" v={q.metrics.citation_accuracy} />
            <Metric label="Answer OK" v={q.metrics.answer_correctness} />
            <Metric label="Latency avg" v={q.metrics.latency_ms_avg / 1000} suffix="s" raw />
          </div>
          <div className="text-[11px] text-ink-faint">
            {q.n_cases} curated cases · generated {q.generated_at ? new Date(q.generated_at).toLocaleString("en-GB") : "—"} ·
            computed live against this document set (not a benchmark claim).
          </div>
          <div className="max-h-80 overflow-y-auto rounded-lg border border-line">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-raised">
                <tr className="text-left text-[10px] uppercase tracking-wider text-ink-faint">
                  <th className="px-3 py-2 font-medium">Question</th>
                  <th className="px-2 py-2 font-medium">Expected</th>
                  <th className="px-2 py-2 font-medium">Top-1</th>
                  <th className="px-2 py-2 text-right font-medium">P@1</th>
                  <th className="px-2 py-2 text-right font-medium">Cite</th>
                  <th className="px-2 py-2 text-right font-medium">OK</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {q.rows.map((r) => (
                  <tr key={r.id} title={r.answer}>
                    <td className="max-w-[220px] truncate px-3 py-2 text-ink-dim">{r.question}</td>
                    <td className="px-2 py-2 font-mono text-[10px] text-ink-faint">{r.expected_doc}</td>
                    <td className="px-2 py-2 font-mono text-[10px] text-ink-faint">{r.top1_doc || "—"}</td>
                    <td className={`px-2 py-2 text-right tabular-nums ${r.precision_at_1 ? "text-emerald-300" : "text-rose-300"}`}>
                      {r.precision_at_1}
                    </td>
                    <td className={`px-2 py-2 text-right tabular-nums ${r.citation_accuracy ? "text-emerald-300" : "text-rose-300"}`}>
                      {r.citation_accuracy}
                    </td>
                    <td className={`px-2 py-2 text-right tabular-nums ${r.answer_correctness ? "text-emerald-300" : "text-rose-300"}`}>
                      {r.answer_correctness}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

function Metric({ label, v, suffix = "", raw = false }: { label: string; v: number; suffix?: string; raw?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-raised/40 p-3">
      <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums text-ink">
        {raw ? v.toFixed(2) : `${Math.round(v * 100)}%`}
        {suffix}
      </div>
    </div>
  );
}
