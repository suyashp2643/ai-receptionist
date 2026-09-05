"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { ApiError } from "@/lib/api";
import {
  CONNECTOR_TYPE_LABELS,
  CONNECTOR_TYPES,
  PII_EVENT_TYPES,
  SAFETY_EVENT_TYPES,
  allowedEventTypesFor,
  connectorRequiresDestinationUrl,
  connectorRequiresSigningSecret,
  createIntegration,
  type ConnectorType,
} from "@/lib/integrations-api";

function NewIntegrationBody({ tenantId }: { tenantId: string }) {
  const router = useRouter();
  const [connectorType, setConnectorType] = useState<ConnectorType>("mock");
  const [name, setName] = useState("");
  const [destinationUrl, setDestinationUrl] = useState("");
  const [signingSecret, setSigningSecret] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requiresUrl = connectorRequiresDestinationUrl(connectorType);
  const requiresSecret = connectorRequiresSigningSecret(connectorType);
  const availableEvents = allowedEventTypesFor(connectorType);

  function toggleEvent(eventType: string) {
    setSelectedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(eventType)) next.delete(eventType);
      else next.add(eventType);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const config: Record<string, unknown> = {};
      if (requiresUrl) config.destination_url = destinationUrl;
      const created = await createIntegration(tenantId, {
        connector_type: connectorType,
        name,
        config,
        enabled_event_types: Array.from(selectedEvents),
        signing_secret: requiresSecret ? signingSecret : null,
      });
      router.push(`/dashboard/integrations/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Could not create this integration.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <Link href="/dashboard/integrations" className="text-sm text-neutral-500">
        ← All integrations
      </Link>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5" aria-label="Create integration">
        <div className="flex flex-col gap-1">
          <label htmlFor="connector-type" className="text-sm font-medium">
            Connector type
          </label>
          <select
            id="connector-type"
            value={connectorType}
            onChange={(e) => {
              const next = e.target.value as ConnectorType;
              setConnectorType(next);
              setSelectedEvents((prev) => {
                const allowed = new Set<string>(allowedEventTypesFor(next));
                return new Set(Array.from(prev).filter((et) => allowed.has(et)));
              });
            }}
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-sm"
          >
            {CONNECTOR_TYPES.map((t) => (
              <option key={t} value={t}>
                {CONNECTOR_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
          {connectorType === "mock" && (
            <p className="text-xs text-neutral-500">
              Deterministic, zero-network — never reaches a real destination. Use this for testing or the integration
              lab.
            </p>
          )}
          {connectorType === "sales_employee" && (
            <p className="text-xs text-neutral-500">
              Outbound notifications only — nothing in this platform sends an email, call, or message on a lead&apos;s
              behalf. Safety-related events can never be enabled on this connector type.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="integration-name" className="text-sm font-medium">
            Name
          </label>
          <input
            id="integration-name"
            required
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-sm"
            placeholder="e.g. Revenue Brain (production)"
          />
        </div>

        {requiresUrl && (
          <div className="flex flex-col gap-1">
            <label htmlFor="destination-url" className="text-sm font-medium">
              Destination URL
            </label>
            <input
              id="destination-url"
              required
              type="url"
              value={destinationUrl}
              onChange={(e) => setDestinationUrl(e.target.value)}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-sm font-mono"
              placeholder="https://example.com/webhooks/ai-receptionist"
            />
            <p className="text-xs text-neutral-500">
              Must be HTTPS in production. Private, loopback, link-local, and reserved addresses are always rejected.
            </p>
          </div>
        )}

        {requiresSecret && (
          <div className="flex flex-col gap-1">
            <label htmlFor="signing-secret" className="text-sm font-medium">
              Signing secret
            </label>
            <input
              id="signing-secret"
              required
              type="password"
              autoComplete="new-password"
              value={signingSecret}
              onChange={(e) => setSigningSecret(e.target.value)}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-sm font-mono"
              placeholder="A shared secret only you and the receiver know"
            />
            <p className="text-xs text-neutral-500">
              Used to sign every delivery with HMAC-SHA256, and encrypted at rest. Never shown again after you leave
              this page — rotate it from the connection&apos;s detail page if you lose it.
            </p>
          </div>
        )}

        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium mb-1">Events to send</legend>
          <div className="flex flex-col gap-2 rounded-lg border border-black/10 dark:border-white/10 p-3 max-h-72 overflow-y-auto">
            {availableEvents.map((eventType) => (
              <label key={eventType} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={selectedEvents.has(eventType)}
                  onChange={() => toggleEvent(eventType)}
                  className="mt-0.5"
                />
                <span className="flex flex-col">
                  <span className="font-mono">{eventType}</span>
                  {PII_EVENT_TYPES.has(eventType) && (
                    <span className="text-xs text-amber-700 dark:text-amber-400">
                      Includes contact details (name/email/phone) captured from a visitor. Only enable this if your
                      receiver is authorized to handle personal data for this purpose.
                    </span>
                  )}
                  {SAFETY_EVENT_TYPES.has(eventType) && (
                    <span className="text-xs text-amber-700 dark:text-amber-400">
                      A safety-relevant classification only (never the triggering message). Intended for human
                      review, not an automated workflow.
                    </span>
                  )}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {error && (
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={submitting || !name}
            className="rounded bg-foreground text-background px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {submitting ? "Creating…" : "Create integration"}
          </button>
          <Link
            href="/dashboard/integrations"
            className="rounded border border-black/15 dark:border-white/20 px-4 py-2 text-sm"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}

export default function NewIntegrationPage() {
  const { tenantId, canManage } = useDashboardContext();
  if (!canManage) {
    return (
      <>
        <h1 className="text-xl font-semibold tracking-tight">New integration</h1>
        <p className="text-sm text-neutral-500 mt-2">Only an owner or admin can create an integration.</p>
      </>
    );
  }
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">New integration</h1>
      <NewIntegrationBody tenantId={tenantId} />
    </>
  );
}
