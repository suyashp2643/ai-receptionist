import { getApiBaseUrl, getCsrfCookieName } from "@/lib/config";

// The short-lived access token lives ONLY in this module-level variable
// (backed by React state in AuthProvider) — never in localStorage or a
// non-HttpOnly cookie. A page reload loses it; refreshAccessToken() (backed
// by the HttpOnly refresh cookie) is how a session survives a reload.
let currentAccessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  currentAccessToken = token;
}

export function getAccessToken(): string | null {
  return currentAccessToken;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function rawRequest(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  if (currentAccessToken) {
    headers.set("Authorization", `Bearer ${currentAccessToken}`);
  }
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers,
    credentials: "include", // required for the HttpOnly refresh cookie
  });
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body?.error?.message ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

/** Uses the HttpOnly refresh cookie (via the browser, automatically) plus
 * the double-submit CSRF cookie to obtain a fresh access token. */
export async function refreshAccessToken(): Promise<boolean> {
  const csrfToken = readCookie(getCsrfCookieName());
  const response = await rawRequest("/api/v1/auth/refresh", {
    method: "POST",
    headers: csrfToken ? { "X-CSRF-Token": csrfToken } : undefined,
  });
  if (!response.ok) {
    setAccessToken(null);
    return false;
  }
  const data = await response.json();
  setAccessToken(data.access_token as string);
  return true;
}

/** For ordinary bearer-token-authenticated calls. Retries once through a
 * silent refresh on 401 (e.g. the access token expired mid-session). */
export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response = await rawRequest(path, options);

  if (response.status === 401 && path !== "/api/v1/auth/refresh") {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await rawRequest(path, options);
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** For the cookie-authenticated state-changing routes (/auth/logout) that
 * require the double-submit CSRF header. */
export async function apiRequestWithCsrf<T>(path: string, options: RequestInit = {}): Promise<T> {
  const csrfToken = readCookie(getCsrfCookieName());
  const headers = new Headers(options.headers);
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  return apiRequest<T>(path, { ...options, headers });
}
