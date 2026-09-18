import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, uploadDocument } from "../lib/api";
import type { Document, DocumentDetail } from "../lib/types";
import { Badge, Card, Empty, ErrorNote, Spinner, StatusBadge } from "../components/ui";
import { bytes, fmtDateTime, pct } from "../lib/format";

const TYPE_TONE: Record<string, "accent" | "violet" | "warn" | "good" | "neutral"> = {
  INSURANCE: "violet",
  BILL: "warn",
  CONTRACT: "accent",
  SUBSCRIPTION: "good",
  BANK_STATEMENT: "accent",
  WARRANTY: "good",
  TRAVEL: "violet",
  INVOICE: "warn",
  RECEIPT: "neutral",
};

export default function DocumentsPage() {
  const client = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const docs = useQuery<Document[]>({
    queryKey: ["documents"],
    queryFn: () => api<Document[]>("/documents"),
    refetchInterval: (q) =>
      q.state.data?.some((d) => d.status === "UPLOADED" || d.status === "PROCESSING" || d.status === "INDEXING") ? 2000 : false,
  });
  // Auto-select the first document once the list loads, without an effect:
  // derive the effective id at render time and only fall back to it when
  // the user hasn't explicitly picked one yet.
  const effectiveSelected = selected ?? docs.data?.[0]?.id ?? null;
  const detail = useQuery<DocumentDetail>(
    {
      queryKey: ["document", effectiveSelected],
      queryFn: () => api<DocumentDetail>(`/documents/${effectiveSelected}`),
      enabled: !!effectiveSelected,
    },
  );

  const doUpload = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    try {
      const doc = (await uploadDocument(file)) as Document;
      await client.invalidateQueries({ queryKey: ["documents"] });
      setSelected(doc.id);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("Delete this document and its derived data (chunks, entities, deadlines)?")) return;
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      await client.invalidateQueries();
      setSelected(null);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="mt-1 text-sm text-ink-faint">
            PDF, DOCX, TXT, MD, CSV (transactions) and images (OCR when enabled). Uploads are
            validated, then processed asynchronously.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void doUpload(f);
            }}
          />
          <button className="btn btn-primary" disabled={uploading} onClick={() => fileRef.current?.click()}>
            {uploading ? "Uploading…" : "＋ Upload document"}
          </button>
        </div>
      </header>

      {uploadError && <ErrorNote message={uploadError} />}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card title={`Vault (${docs.data?.length ?? 0})`} className="lg:col-span-2">
          {!docs.data ? (
            <Spinner />
          ) : docs.data.length === 0 ? (
            <Empty
              title="No documents yet"
              hint="Upload a bill, policy, contract or a transactions CSV. NEXUS classifies it, extracts entities and derives deadlines automatically."
            />
          ) : (
            <ul className="space-y-2">
              {docs.data.map((d) => (
                <li key={d.id}>
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelected(d.id)}
                    onKeyDown={(e) => e.key === "Enter" && setSelected(d.id)}
                    className={`w-full cursor-pointer rounded-lg border p-3 text-left transition-colors ${
                      effectiveSelected === d.id ? "border-accent/40 bg-accent/5" : "border-line bg-raised/30 hover:border-line/80"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-sm text-ink">{d.filename}</span>
                      <button
                        className="shrink-0 rounded px-1.5 text-xs text-ink-faint hover:text-rose-300"
                        title="Delete document"
                        onClick={(e) => {
                          e.stopPropagation();
                          void remove(d.id);
                        }}
                      >
                        ✕
                      </button>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-ink-faint">
                      <StatusBadge status={d.status} />
                      <Badge tone={TYPE_TONE[d.doc_type] ?? "neutral"}>{d.doc_type}</Badge>
                      <span>{pct(d.doc_type_confidence)} conf</span>
                      <span>·</span>
                      <span>{bytes(d.size_bytes)}</span>
                      <span>·</span>
                      <span>{fmtDateTime(d.created_at)}</span>
                    </div>
                    {d.status === "FAILED" && (
                      <div className="mt-2 rounded border border-rose-500/20 bg-rose-500/5 px-2 py-1 text-[11px] text-rose-300">
                        {d.status_detail}
                      </div>
                    )}
                    {d.status === "READY" && (
                      <div className="mt-1 truncate text-[11px] text-ink-faint">{d.status_detail}</div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Document intelligence" className="lg:col-span-3">
          {detail.isLoading ? (
            <Spinner />
          ) : detail.data ? (
            <div className="space-y-5">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-ink">{detail.data.filename}</span>
                  <StatusBadge status={detail.data.status} />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-3 text-xs text-ink-dim md:grid-cols-4">
                  <Meta k="Type" v={`${detail.data.doc_type} (${pct(detail.data.doc_type_confidence)})`} />
                  <Meta k="Format" v={detail.data.file_type} />
                  <Meta k="Pages" v={String(detail.data.page_count)} />
                  <Meta k="Chunks" v={String(detail.data.chunk_count)} />
                </div>
              </div>

              {detail.data.entities.length > 0 && (
                <div>
                  <div className="panel-title mb-2">Extracted entities</div>
                  <div className="flex flex-wrap gap-2">
                    {detail.data.entities.map((e, i) => (
                      <span
                        key={i}
                        title={`${e.evidence} (conf ${Math.round(e.confidence * 100)}%)`}
                        className="group cursor-help rounded-md border border-line bg-raised/50 px-2 py-1 text-xs text-ink-dim hover:border-accent/40"
                      >
                        <span className="mr-1.5 rounded bg-line px-1 py-0.5 text-[9px] uppercase tracking-wider text-ink-faint">
                          {e.kind}
                        </span>
                        {e.value}
                        <span className="ml-1.5 text-[10px] text-ink-faint">{Math.round(e.confidence * 100)}%</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {detail.data.chunks.length > 0 && (
                <div>
                  <div className="panel-title mb-2">Index chunks</div>
                  <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                    {detail.data.chunks.map((c) => (
                      <div key={c.id} className="rounded-lg border border-line bg-raised/30 p-3">
                        <div className="mb-1 flex gap-2 text-[10px] uppercase tracking-wider text-ink-faint">
                          <span>chunk {c.chunk_index}</span>
                          <span>·</span>
                          <span>page {c.page}</span>
                          <span>·</span>
                          <span>{c.text.length} chars</span>
                        </div>
                        <p className="whitespace-pre-wrap text-xs leading-relaxed text-ink-dim">{c.text.slice(0, 600)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {detail.data.text_preview && detail.data.chunks.length === 0 && (
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-ink-dim">{detail.data.text_preview.slice(0, 1200)}</p>
              )}
            </div>
          ) : (
            <Empty title="Select a document" />
          )}
        </Card>
      </div>
    </div>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-lg border border-line bg-raised/30 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-ink-faint">{k}</div>
      <div className="mt-0.5 font-medium text-ink">{v}</div>
    </div>
  );
}
