import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { clearToken, setToken } from "./lib/api";

/** Minimal per-path fixtures so any component mounted along a route can
 * resolve its queries instead of sitting in an error/loading state that
 * would make assertions timing-dependent. */
function mockBackend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = url.replace(/^\/api\/v1/, "");
      const body: Record<string, unknown> = {
        "/auth/me": { id: "u1", email: "demo@nexus.dev", name: "Demo User", created_at: "2026-01-01T00:00:00Z" },
        "/health": { status: "ok", service: "nexus-api", version: "0.1.0", llm_provider: "mock", embed_provider: "hash", db: "sqlite", pgvector: false },
        "/notifications": [],
        "/insights/overview": {
          needs_attention: 0, upcoming: 0, risk_signals: 0, recurring_monthly: 0,
          recurring_currency: "INR", documents: 0, ready_documents: 0, pending_documents: 0,
          knowledge_coverage: 0, pending_approvals: 0, recent: [],
        },
        "/insights/deadlines": [],
        "/insights/subscriptions": [],
      };
      const key = Object.keys(body).find((k) => path.startsWith(k));
      return {
        status: 200,
        ok: true,
        json: async () => (key ? body[key] : {}),
      } as Response;
    }),
  );
}

function renderApp(initialPath: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("routing and auth gating", () => {
  beforeEach(() => {
    clearToken();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("redirects an unauthenticated visitor from / to the login form", async () => {
    renderApp("/");
    expect(await screen.findByText(/create account/i)).toBeInTheDocument();
  });

  it("redirects an authenticated visitor away from /login to the dashboard", async () => {
    mockBackend();
    setToken("valid-token");
    renderApp("/login");
    expect(await screen.findByText("Command Overview")).toBeInTheDocument();
    expect(screen.queryByText(/create account/i)).not.toBeInTheDocument();
  });

  it("shows the 404 page for an unmatched authenticated route", async () => {
    mockBackend();
    setToken("valid-token");
    renderApp("/this-does-not-exist");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});
