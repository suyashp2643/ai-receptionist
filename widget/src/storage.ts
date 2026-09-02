/**
 * Persists the visitor's capability token + conversation id in
 * `sessionStorage`, scoped per widget installation (`publicId`) — this is
 * what makes "close the widget panel, reopen it, resume the same
 * conversation" and "reload the page, resume the same conversation" work.
 * Deliberately `sessionStorage`, not `localStorage`: the token is a
 * capability (see WidgetVisitorSession's docstring in the backend) and
 * should not persist indefinitely across browser restarts. If storage is
 * unavailable (private browsing, blocked site data), every method here
 * degrades to a no-op/miss rather than throwing — the widget still works,
 * it just starts a fresh conversation every time.
 *
 * The optional `namespace` exists for the dashboard's "live local preview"
 * feature only: a real embed never passes one, so its storage key is
 * exactly as before. The preview page generates a fresh random namespace
 * on each "Restart preview" click, which is enough on its own to make
 * `loadStoredSession` miss (a genuinely different key) without needing to
 * reach into another frame's storage or guess at clearing the right key.
 */

interface StoredSession {
  token: string;
  conversationId: string;
}

function storageKey(publicId: string, namespace?: string): string {
  return namespace ? `ai-receptionist-widget:${publicId}:${namespace}` : `ai-receptionist-widget:${publicId}`;
}

export function loadStoredSession(publicId: string, namespace?: string): StoredSession | null {
  try {
    const raw = window.sessionStorage.getItem(storageKey(publicId, namespace));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (typeof parsed.token === "string" && typeof parsed.conversationId === "string") {
      return { token: parsed.token, conversationId: parsed.conversationId };
    }
    return null;
  } catch {
    return null;
  }
}

export function saveStoredSession(publicId: string, session: StoredSession, namespace?: string): void {
  try {
    window.sessionStorage.setItem(storageKey(publicId, namespace), JSON.stringify(session));
  } catch {
    // Ignored — see module docstring.
  }
}

export function clearStoredSession(publicId: string, namespace?: string): void {
  try {
    window.sessionStorage.removeItem(storageKey(publicId, namespace));
  } catch {
    // Ignored — see module docstring.
  }
}
