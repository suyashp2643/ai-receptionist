export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

// Matches backend's Settings.widget_bundle_url default — see its docstring
// in backend/app/config.py and docs/local-development.md's documented
// `cd widget && python3 -m http.server 5174` command. Used by the public
// marketing site's /demo/* pages (Phase 7), which have no dashboard
// session to fetch a per-installation embed snippet from.
export function getWidgetBundleUrl(): string {
  return process.env.NEXT_PUBLIC_WIDGET_BUNDLE_URL ?? "http://localhost:5174/dist/widget.js";
}

// Must match the backend's CSRF_COOKIE_NAME (see backend/.env.example) —
// it's a cookie *name*, not a secret, so it's safe to expose via NEXT_PUBLIC_.
export function getCsrfCookieName(): string {
  return process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME ?? "ai_receptionist_csrf";
}
