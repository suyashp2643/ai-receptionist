export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

// Must match the backend's CSRF_COOKIE_NAME (see backend/.env.example) —
// it's a cookie *name*, not a secret, so it's safe to expose via NEXT_PUBLIC_.
export function getCsrfCookieName(): string {
  return process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME ?? "ai_receptionist_csrf";
}
