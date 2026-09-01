/**
 * AI Receptionist embeddable widget — package foundation only.
 *
 * Full implementation (launcher, conversation UI, voice, streaming, contact
 * capture, appointment/handoff requests) is planned for Phase 5 and will
 * talk exclusively to the public widget API surface (/api/v1/widget/*),
 * never to internal tenant-scoped endpoints.
 */

export const WIDGET_FOUNDATION_VERSION = "0.1.0";

export interface WidgetConfig {
  /** Public, revocable receptionist token — never a database ID. */
  publicToken: string;
  /** Optional API base URL override, defaults to the production widget API. */
  apiBaseUrl?: string;
}

/**
 * Placeholder entry point. Intentionally does not render anything yet —
 * real mount/unmount logic is a Phase 5 deliverable.
 */
export function initWidget(config: WidgetConfig): void {
  if (!config.publicToken) {
    throw new Error("initWidget requires a publicToken");
  }
  console.info("[ai-receptionist widget] foundation package loaded; UI not yet implemented");
}
