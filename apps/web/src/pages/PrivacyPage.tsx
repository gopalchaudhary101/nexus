import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, clearToken } from "../lib/api";
import type { AnalyticsOverview } from "../lib/types";
import { Card, ErrorNote, Spinner } from "../components/ui";
import { bytes } from "../lib/format";

const DATA_CATEGORIES: [string, keyof AnalyticsOverview, string][] = [
  ["Documents (files, extracted text, index chunks)", "documents", "Deleted from Documents removes a single document's data immediately."],
  ["Search index chunks", "chunks", "Derived from your documents; removed with the source document."],
  ["Transactions", "transactions", "Imported from CSV uploads."],
  ["Subscriptions detected", "subscriptions", "Derived from transaction and document patterns."],
  ["Deadlines extracted", "deadlines", "Derived from document content."],
  ["Risk assessments run", "risks", "Messages you submitted to the Risk Center — text is not retained beyond the assessment record."],
  ["Agent runs", "agent_runs", "Full trace of tool calls, approvals and results."],
  ["Audit events", "audit_events", "Append-only log of consequential actions and decisions."],
];

export default function PrivacyPage() {
  const navigate = useNavigate();
  const overview = useQuery<AnalyticsOverview>({
    queryKey: ["analytics-overview"],
    queryFn: () => api<AnalyticsOverview>("/analytics/overview"),
  });

  const [password, setPassword] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canDelete = confirmText.trim().toUpperCase() === "DELETE" && password.length > 0;

  const submitDelete = async (e: FormEvent) => {
    e.preventDefault();
    if (!canDelete) return;
    setError(null);
    setBusy(true);
    try {
      await api<void>("/auth/me", { method: "DELETE", body: { password } });
      clearToken();
      navigate("/login");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Privacy &amp; data</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-faint">
          Everything NEXUS knows about you comes from what you've uploaded or entered
          yourself. Nothing here is shared across accounts, used to train a shared
          model, or sold — every query in the system is scoped to your own user id.
        </p>
      </header>

      <Card title="What's stored on your account">
        {overview.isError && <ErrorNote message={String(overview.error)} />}
        {overview.isLoading ? (
          <Spinner label="Loading account data…" />
        ) : (
          <>
            <ul className="divide-y divide-line">
              {DATA_CATEGORIES.map(([label, key, hint]) => (
                <li key={key} className="flex items-start justify-between gap-4 py-3">
                  <div>
                    <div className="text-sm text-ink">{label}</div>
                    <div className="mt-0.5 text-xs text-ink-faint">{hint}</div>
                  </div>
                  <span className="shrink-0 tabular-nums text-sm font-medium text-ink-dim">
                    {overview.data?.[key] ?? 0}
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-3 flex items-center justify-between border-t border-line pt-3 text-xs text-ink-faint">
              <span>Storage used by uploaded files</span>
              <span className="tabular-nums">{bytes(overview.data?.storage_bytes ?? 0)}</span>
            </div>
          </>
        )}
      </Card>

      <Card title="Delete individual documents">
        <p className="text-sm text-ink-dim">
          Deleting a single document (and everything derived from it — chunks,
          entities, deadlines, graph nodes) doesn't require deleting your whole
          account. Do this from the{" "}
          <Link to="/documents" className="text-accent hover:underline">
            Documents
          </Link>{" "}
          page.
        </p>
      </Card>

      <Card title="Delete your account" className="border-rose-500/30">
        <p className="text-sm text-ink-dim">
          This permanently deletes your account and every row associated with it —
          documents, transactions, agent runs, approvals and notifications. This
          cannot be undone. The fact that an account was deleted (not its content)
          remains in the audit log, as it does for any consequential action.
        </p>
        <form onSubmit={submitDelete} className="mt-4 max-w-sm space-y-3">
          <div>
            <label htmlFor="delete-account-password" className="mb-1.5 block text-xs font-medium text-ink-dim">
              Your password
            </label>
            <input
              id="delete-account-password"
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div>
            <label htmlFor="delete-account-confirm" className="mb-1.5 block text-xs font-medium text-ink-dim">
              Type DELETE to confirm
            </label>
            <input
              id="delete-account-confirm"
              className="input"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="DELETE"
            />
          </div>
          {error && <ErrorNote message={error} />}
          <button type="submit" className="btn btn-danger" disabled={!canDelete || busy}>
            {busy ? "Deleting…" : "Permanently delete my account"}
          </button>
        </form>
      </Card>
    </div>
  );
}
