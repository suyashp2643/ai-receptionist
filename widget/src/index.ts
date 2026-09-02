/**
 * AI Receptionist embeddable widget — Phase 5.
 *
 * Self-initializing from its own <script> tag's data-* attributes (see
 * README.md / docs for the exact snippet):
 *
 *   <script src="WIDGET_BUNDLE_URL" data-receptionist-id="PUBLIC_WIDGET_ID" async></script>
 *
 * `document.currentScript` is read synchronously at the top of this
 * module's execution, before any `await` — that is the one point in an
 * async-loaded script's lifetime where `document.currentScript` is
 * guaranteed to still point at this script's own tag (it becomes null
 * once any microtask/macrotask boundary is crossed). Everything after
 * that point is async, but the attributes have already been captured.
 *
 * Talks exclusively to the public widget API (/api/v1/widget/*) — never to
 * any internal tenant-scoped endpoint — and never accepts a tenant UUID,
 * system prompt, or any other private configuration from this snippet;
 * everything it renders comes from the server's public config response.
 *
 * Two additional, optional attributes exist solely for the dashboard's
 * "live local preview" feature (see widget-preview.html and
 * docs/architecture.md) — a real customer embed never sets either:
 *   - `data-visitor-reference`: threaded into every session-creation call's
 *     `visitor_reference`, so preview traffic is distinguishable from real
 *     visitors in a tenant's own records.
 *   - `data-session-namespace`: namespaces this instance's sessionStorage
 *     key, so the preview page's "Restart preview" can force a brand-new
 *     conversation by generating a fresh namespace.
 */
import { Widget } from "./ui";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const MOUNT_MARKER_ATTR = "data-ai-receptionist-widget-mounted";

interface WidgetGlobal {
  instances: Map<string, Widget>;
}

function getGlobal(): WidgetGlobal {
  const w = window as unknown as { __aiReceptionistWidget?: WidgetGlobal };
  if (!w.__aiReceptionistWidget) {
    w.__aiReceptionistWidget = { instances: new Map() };
  }
  return w.__aiReceptionistWidget;
}

interface OwnScriptAttributes {
  publicId: string | null;
  apiBaseUrl: string;
  visitorReference?: string;
  sessionNamespace?: string;
}

function readOwnScriptAttributes(): OwnScriptAttributes {
  const script = document.currentScript as HTMLScriptElement | null;
  const publicId = script?.getAttribute("data-receptionist-id") ?? null;
  const apiBaseUrl = script?.getAttribute("data-api-base-url") ?? DEFAULT_API_BASE_URL;
  const visitorReference = script?.getAttribute("data-visitor-reference") ?? undefined;
  const sessionNamespace = script?.getAttribute("data-session-namespace") ?? undefined;
  return { publicId, apiBaseUrl, visitorReference, sessionNamespace };
}

function init(attrs: OwnScriptAttributes & { publicId: string }): void {
  const registry = getGlobal();
  const registryKey = attrs.sessionNamespace ? `${attrs.publicId}:${attrs.sessionNamespace}` : attrs.publicId;
  if (registry.instances.has(registryKey)) {
    // Duplicate initialization for the same widget (e.g. the snippet was
    // pasted twice, or a bundler double-executed this module) — a no-op,
    // not a second panel/launcher.
    return;
  }
  if (document.querySelector(`[${MOUNT_MARKER_ATTR}="${CSS.escape(registryKey)}"]`)) return;

  const host = document.createElement("div");
  host.setAttribute(MOUNT_MARKER_ATTR, registryKey);
  document.body.appendChild(host);

  const widget = new Widget(
    {
      publicId: attrs.publicId,
      apiBaseUrl: attrs.apiBaseUrl,
      visitorReference: attrs.visitorReference,
      sessionNamespace: attrs.sessionNamespace,
    },
    host
  );
  registry.instances.set(registryKey, widget);
  void widget.mount();
}

/** Exposed for programmatic control/testing — not required for the basic
 * `<script data-receptionist-id>` embed, which self-initializes below. */
export function destroyWidget(publicId: string): void {
  const registry = getGlobal();
  const widget = registry.instances.get(publicId);
  if (!widget) return;
  widget.destroy();
  registry.instances.delete(publicId);
}

export { Widget };

const attrs = readOwnScriptAttributes();
if (attrs.publicId) {
  const ready = { ...attrs, publicId: attrs.publicId };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => init(ready));
  } else {
    init(ready);
  }
}
