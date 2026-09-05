import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest, getAccessToken, refreshAccessToken, setAccessToken } from "./api";

function jsonResponse(body: unknown, init: { status?: number } = {}): Response {
  return {
    ok: (init.status ?? 200) < 400,
    status: init.status ?? 200,
    json: async () => body,
  } as unknown as Response;
}

function clearCookies() {
  // jsdom's document.cookie setter accepts one cookie-string per assignment;
  // expiring known names is the simplest reliable way to reset between tests.
  document.cookie = "ai_receptionist_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

beforeEach(() => {
  clearCookies();
  setAccessToken(null);
});

afterEach(() => {
  clearCookies();
  setAccessToken(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("refreshAccessToken", () => {
  it("reads the CSRF cookie and sends it as X-CSRF-Token, storing the returned access token in memory only", async () => {
    document.cookie = "ai_receptionist_csrf=my-csrf-value";
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("my-csrf-value");
      return jsonResponse({ access_token: "new-access-token" });
    });
    vi.stubGlobal("fetch", fetchMock);

    const ok = await refreshAccessToken();

    expect(ok).toBe(true);
    expect(getAccessToken()).toBe("new-access-token");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/auth/refresh");
    expect((init as RequestInit).credentials).toBe("include");
  });

  it("sends no X-CSRF-Token header when the cookie is absent (never fabricates one)", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect((init?.headers as Headers | undefined)?.get?.("X-CSRF-Token") ?? null).toBeFalsy();
      return jsonResponse({ access_token: "irrelevant" });
    });
    vi.stubGlobal("fetch", fetchMock);

    await refreshAccessToken();
    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.has("X-CSRF-Token")).toBe(false);
  });

  it("returns false and clears the access token on failure (e.g. CSRF rejection or a revoked/expired session)", async () => {
    setAccessToken("stale-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ error: { message: "CSRF validation failed." } }, { status: 403 }))
    );

    const ok = await refreshAccessToken();

    expect(ok).toBe(false);
    expect(getAccessToken()).toBeNull();
  });

  it("de-dupes concurrent callers onto exactly one in-flight request", async () => {
    let resolveResponse!: (r: Response) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveResponse = resolve;
        })
    );
    vi.stubGlobal("fetch", fetchMock);

    // Simulates two components (or React Strict Mode's deliberate
    // double-invoke of a mount effect) each independently calling
    // refreshAccessToken() before the first has resolved.
    const first = refreshAccessToken();
    const second = refreshAccessToken();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveResponse(jsonResponse({ access_token: "shared-token" }));

    const [firstResult, secondResult] = await Promise.all([first, second]);
    expect(firstResult).toBe(true);
    expect(secondResult).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBe("shared-token");
  });

  it("starts a genuinely new request for a refresh that happens after the previous one already settled", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ access_token: "token-1" }))
      .mockResolvedValueOnce(jsonResponse({ access_token: "token-2" }));
    vi.stubGlobal("fetch", fetchMock);

    await refreshAccessToken();
    await refreshAccessToken();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getAccessToken()).toBe("token-2");
  });

  it("never writes the access token, or anything else, to localStorage or sessionStorage", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ access_token: "should-stay-in-memory" })));
    await refreshAccessToken();
    expect(Object.keys(localStorage)).toHaveLength(0);
    expect(Object.keys(sessionStorage)).toHaveLength(0);
  });
});

describe("apiRequest", () => {
  it("retries once via a silent refresh after a 401, then succeeds", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: { message: "Not authenticated" } }, { status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ access_token: "refreshed-token" }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiRequest<{ ok: boolean }>("/api/v1/tenants/t1/integrations");

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1][0])).toContain("/api/v1/auth/refresh");
  });

  it("does not attempt a refresh loop when the refresh call itself 401s", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: { message: "Invalid credentials." } }, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/api/v1/auth/refresh", { method: "POST" })).rejects.toBeInstanceOf(ApiError);
    // Exactly the one direct call — no self-triggered retry-via-refresh.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces a non-401 failure as an ApiError without attempting a refresh", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: { message: "Not found" } }, { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/api/v1/tenants/t1/integrations/missing")).rejects.toMatchObject({ status: 404 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
