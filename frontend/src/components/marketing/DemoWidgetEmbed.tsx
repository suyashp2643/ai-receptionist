"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getApiBaseUrl, getWidgetBundleUrl } from "@/lib/config";

function newSessionNamespace(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Embeds the real, unmodified public widget bundle for one demo
 * installation via the sandboxed /demo-widget.html page (same pattern as
 * the dashboard's own live-preview iframe — see
 * frontend/src/app/dashboard/receptionist/widget/page.tsx and
 * frontend/public/widget-preview.html). Each demo gets its OWN session
 * namespace, generated fresh per mount and on "Restart demo" — never
 * shared across the three demos, and never persisted, so restarting one
 * demo cannot restore or affect another's session.
 */
export function DemoWidgetEmbed({
  publicId,
  title,
  height = 560,
}: {
  publicId: string;
  title: string;
  height?: number;
}) {
  // Generated client-side only, after mount — never during the initial
  // render, which Next.js also executes on the server for SSR. A random
  // value computed during that server render would never match the value
  // computed during client hydration, producing a hydration mismatch on
  // the iframe's src. Starting from null and setting the real value in an
  // effect keeps server and client markup identical until the browser
  // takes over.
  const [sessionNamespace, setSessionNamespace] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);
  const restartButtonRef = useRef<HTMLButtonElement>(null);
  const liveRegionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSessionNamespace(newSessionNamespace());
  }, []);

  const restart = useCallback(() => {
    setLoadError(false);
    setSessionNamespace(newSessionNamespace());
    if (liveRegionRef.current) {
      liveRegionRef.current.textContent = "Demo restarted. Starting a new, isolated conversation.";
    }
  }, []);

  const src = sessionNamespace
    ? `/demo-widget.html?${new URLSearchParams({
        publicId,
        apiBaseUrl: getApiBaseUrl(),
        bundleUrl: getWidgetBundleUrl(),
        sessionNamespace,
      }).toString()}`
    : null;

  return (
    <div className="flex flex-col gap-3">
      <div
        className="overflow-hidden rounded-2xl border border-white/10 bg-mark-surface shadow-2xl shadow-black/40"
        style={{ height }}
      >
        {src && (
          <iframe
            key={sessionNamespace}
            src={src}
            title={title}
            sandbox="allow-scripts allow-same-origin allow-forms"
            style={{ width: "100%", height, border: "none", display: "block" }}
            onError={() => setLoadError(true)}
          />
        )}
      </div>
      <div ref={liveRegionRef} role="status" aria-live="polite" className="sr-only" />
      {loadError && (
        <p role="alert" className="text-sm text-amber-300">
          The demo widget could not load. It may be temporarily unavailable — try restarting the demo below.
        </p>
      )}
      <button
        ref={restartButtonRef}
        type="button"
        onClick={restart}
        className="inline-flex w-fit items-center gap-2 rounded-full border border-mark-border px-4 py-2 text-xs font-semibold text-white/80 transition hover:border-mark-violet-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400"
      >
        Restart demo
      </button>
    </div>
  );
}
