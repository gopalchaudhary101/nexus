import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PrivacyPage from "./PrivacyPage";

function renderPrivacyPage() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status: 200,
      ok: true,
      json: async () => ({
        documents: 3, chunks: 10, transactions: 50, subscriptions: 2,
        deadlines: 4, risks: 1, agent_runs: 1, audit_events: 5, storage_bytes: 2048,
      }),
    })),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PrivacyPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PrivacyPage delete-account gating", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the delete button disabled until both a password and DELETE are entered", async () => {
    const user = userEvent.setup();
    renderPrivacyPage();

    const deleteBtn = await screen.findByRole("button", { name: /permanently delete my account/i });
    expect(deleteBtn).toBeDisabled();

    await user.type(screen.getByLabelText(/your password/i), "hunter2");
    expect(deleteBtn).toBeDisabled(); // password alone isn't enough

    await user.type(screen.getByPlaceholderText("DELETE"), "delete"); // case-insensitive
    expect(deleteBtn).toBeEnabled();
  });

  it("stays disabled if the confirmation text doesn't match", async () => {
    const user = userEvent.setup();
    renderPrivacyPage();

    await user.type(await screen.findByLabelText(/your password/i), "hunter2");
    await user.type(screen.getByPlaceholderText("DELETE"), "delet");
    expect(screen.getByRole("button", { name: /permanently delete my account/i })).toBeDisabled();
  });

  it("renders real per-category counts from the account overview, not placeholders", async () => {
    renderPrivacyPage();
    expect(await screen.findByText("50")).toBeInTheDocument(); // transactions
    expect(screen.getByText("3")).toBeInTheDocument(); // documents
  });
});
