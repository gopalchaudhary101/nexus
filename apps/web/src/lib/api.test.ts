import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, clearToken, getToken, setToken } from "./api";

function mockFetchOnce(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  });
}

describe("api()", () => {
  beforeEach(() => {
    clearToken();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches the bearer token when one is set", async () => {
    setToken("test-token-123");
    const fetchMock = mockFetchOnce(200, { ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await api("/health");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer test-token-123");
  });

  it("sends no Authorization header when logged out", async () => {
    const fetchMock = mockFetchOnce(200, { ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await api("/health");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("returns undefined for a 204 No Content response", async () => {
    vi.stubGlobal("fetch", mockFetchOnce(204, null));
    const result = await api("/notifications/abc/read", { method: "POST" });
    expect(result).toBeUndefined();
  });

  it("throws ApiError with the server's status/code/detail on failure", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchOnce(404, { error: { code: "not_found", detail: "Document not found" } }),
    );

    await expect(api("/documents/missing")).rejects.toMatchObject({
      status: 404,
      code: "not_found",
      message: "Document not found",
    });
  });

  it("throws a well-formed ApiError even when the error body isn't the expected shape", async () => {
    vi.stubGlobal("fetch", mockFetchOnce(500, { unexpected: "shape" }));

    const error = await api("/whatever").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(500);
    expect((error as ApiError).code).toBe("error");
  });

  it("sets Content-Type and serializes the body for POST requests", async () => {
    const fetchMock = mockFetchOnce(200, { ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await api("/risk/analyze", { method: "POST", body: { text: "hello" } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ text: "hello" }));
    expect(init.method).toBe("POST");
  });
});

describe("token storage", () => {
  it("round-trips through localStorage", () => {
    expect(getToken()).toBeNull();
    setToken("abc");
    expect(getToken()).toBe("abc");
    clearToken();
    expect(getToken()).toBeNull();
  });
});
