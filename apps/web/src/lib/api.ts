import { z } from "zod";

const TOKEN_KEY = "nexus_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

interface ApiOptions {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
}

/** JSON API client. All paths are relative (/api/v1/...) so the Vite proxy
 * (or same-origin deployment) handles routing. */
export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api/v1${path}`, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    // non-JSON error body
  }
  if (!res.ok) {
    const err = payload as { error?: { code?: string; detail?: string | unknown } } | null;
    const detail =
      typeof err?.error?.detail === "string" ? err.error.detail : JSON.stringify(err ?? "Request failed");
    throw new ApiError(res.status, err?.error?.code ?? "error", detail);
  }
  return payload as T;
}

export async function uploadDocument(file: File): Promise<unknown> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/v1/documents/upload", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!res.ok) {
    const payload = (await res.json().catch(() => null)) as {
      error?: { code?: string; detail?: string };
    } | null;
    throw new ApiError(res.status, payload?.error?.code ?? "error", payload?.error?.detail ?? "Upload failed");
  }
  return res.json();
}

/** Client-side validation (defense in depth; backend validates too). */
export const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});
export const registerSchema = loginSchema.extend({
  name: z.string().min(1).max(120),
});

export async function runAgentSSE(
  request: string,
  onEvent: (evt: AgentSSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken();
  const res = await fetch("/api/v1/agent/run", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token ?? ""}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ request }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Agent run failed (HTTP ${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        onEvent(JSON.parse(line.slice(6)) as AgentSSEEvent);
      }
    }
  }
}

export type AgentSSEEvent =
  | { type: "planner"; intent: string; steps: string[] }
  | { type: "tool"; tool: string; status: "OK" | "FAILED"; summary: string }
  | { type: "gate"; tool: string; approval_id: string; risk_class: string }
  | { type: "final"; response: string }
  | { type: "done"; run_id: string; status: string };
