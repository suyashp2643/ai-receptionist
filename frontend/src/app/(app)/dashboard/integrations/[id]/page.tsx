"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { ErrorState, LoadingState } from "@/components/dashboard/ListStates";
import { ConfirmDialog } from "@/components/dashboard/ConfirmDialog";
import { ApiError } from "@/lib/api";
import {
  CONNECTOR_TYPE_LABELS,
  PII_EVENT_TYPES,
  SAFETY_EVENT_TYPES,
  allowedEventTypesFor,
  connectorRequiresDestinationUrl,
  connectorRequiresSigningSecret,
  disableIntegration,
  generateInboundApiKey,
  getIntegration,
  pauseIntegration,
  previewFieldMapping,
  resumeIntegration,
  rotateSigningSecret,
  sendTestEvent,
  updateIntegration,
  verifyIntegration,
  type IntegrationConnection,
} from "@/lib/integrations-api";

type PendingConfirmation = "disable" | "rotate-secret" | "rotate-inbound-key" | null;

function OneTimeSecretPanel({ apiKey, onDismiss }: { apiKey: string; onDismiss: () => void }) {
  // Held only in this component's own React state (a prop passed down from
  // a parent's useState) — never written to localStorage, sessionStorage,
  // a URL, or any persisted store. Unmounting this component (navigating
  // away, or dismissing) discards it completely; the backend never
  // returns it again on any subsequent request.
  const [copied, setCopied] = useState(false);
  return (
    <div
      role="alertdialog"
      aria-labelledby="one-time-key-title"
      className="rounded-lg border border-green-400 dark:border-green-700 bg-green-50 dark:bg-green-950/30 p-4 flex flex-col gap-2"
    >
      <p id="one-time-key-title" className="font-medium text-green-900 dark:text-green-300">
        Your new inbound API key — copy it now, it will never be shown again
      </p>
      <code className="block rounded bg-white dark:bg-neutral-900 border border-black/10 dark:border-white/10 px-3 py-2 text-sm break-all select-all">
        {apiKey}
      </code>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={async () => {
            await navigator.clipboard.writeText(apiKey);
            setCopied(true);
          }}
          className="rounded bg-foreground text-background px-3 py-1.5 text-sm font-medium"
        >
          {copied ? "Copied" : "Copy to clipboard"}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm"
        >
          I&apos;ve saved it — hide this
        </button>
      </div>
    </div>
  );
}

function MappingEditor({
  tenantId,
  connectionId,
  mapping,
  onChange,
}: {
  tenantId: string;
  connectionId: string;
  mapping: string;
  onChange: (raw: string) => void;
}) {
  const [sampleData, setSampleData] = useState('{\n  "phone": "555-0100",\n  "internal_id": "abc"\n}');
  const [previewResult, setPreviewResult] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);

  async function handlePreview() {
    setPreviewError(null);
    setPreviewResult(null);
    setPreviewing(true);
    try {
      const parsedSample = JSON.parse(sampleData);
      const parsedMapping = mapping.trim() ? JSON.parse(mapping) : {};
      const { result } = await previewFieldMapping(tenantId, connectionId, parsedSample, parsedMapping);
      setPreviewResult(JSON.stringify(result, null, 2));
    } catch (err) {
      if (err instanceof ApiError) setPreviewError(err.message);
      else if (err instanceof SyntaxError) setPreviewError("Sample data or mapping is not valid JSON.");
      else setPreviewError("Could not preview this mapping.");
    } finally {
      setPreviewing(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-neutral-500">
        Controlled field mapping: rename, include, omit, and default only — no code execution. Applied to the
        event&apos;s own data only, never the envelope&apos;s identity fields.
      </p>
      <div className="grid sm:grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="mapping-json" className="text-xs text-neutral-500">
            Mapping (JSON)
          </label>
          <textarea
            id="mapping-json"
            value={mapping}
            onChange={(e) => onChange(e.target.value)}
            rows={8}
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-xs font-mono"
            placeholder='{"rename": {"phone": "phone_number"}, "omit": ["internal_id"]}'
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="sample-data-json" className="text-xs text-neutral-500">
            Fictional sample data (JSON) — preview only, never a real event
          </label>
          <textarea
            id="sample-data-json"
            value={sampleData}
            onChange={(e) => setSampleData(e.target.value)}
            rows={8}
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-xs font-mono"
          />
        </div>
      </div>
      <div>
        <button
          type="button"
          onClick={handlePreview}
          disabled={previewing}
          className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
        >
          {previewing ? "Previewing…" : "Preview transformation"}
        </button>
      </div>
      {previewError && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {previewError}
        </p>
      )}
      {previewResult && (
        <div className="flex flex-col gap-1">
          <p className="text-xs text-neutral-500">What the receiver would get:</p>
          <pre className="rounded bg-black/5 dark:bg-white/5 p-3 text-xs overflow-x-auto">{previewResult}</pre>
        </div>
      )}
    </div>
  );
}

function IntegrationDetailBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<IntegrationConnection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState<PendingConfirmation>(null);

  const [destinationUrl, setDestinationUrl] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<Set<string>>(new Set());
  const [mappingJson, setMappingJson] = useState("");
  const [newSecret, setNewSecret] = useState("");
  const [oneTimeKey, setOneTimeKey] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<{ success: boolean; error_summary: string | null } | null>(null);

  function load() {
    setError(null);
    getIntegration(tenantId, params.id)
      .then((d) => {
        setDetail(d);
        setDestinationUrl((d.config.destination_url as string) ?? "");
        setSelectedEvents(new Set(d.enabled_event_types));
        setMappingJson(d.config.field_mapping ? JSON.stringify(d.config.field_mapping, null, 2) : "");
      })
      .catch(() => setError("Could not load this integration."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, params.id]);

  function toggleEvent(eventType: string) {
    setSelectedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(eventType)) next.delete(eventType);
      else next.add(eventType);
      return next;
    });
  }

  async function handleSaveConfig() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    try {
      const config: Record<string, unknown> = { ...detail.config };
      if (connectorRequiresDestinationUrl(detail.connector_type)) config.destination_url = destinationUrl;
      if (mappingJson.trim()) {
        try {
          config.field_mapping = JSON.parse(mappingJson);
        } catch {
          setActionError("Field mapping is not valid JSON.");
          setBusy(false);
          return;
        }
      } else {
        delete config.field_mapping;
      }
      const updated = await updateIntegration(tenantId, detail.id, {
        config,
        enabled_event_types: Array.from(selectedEvents),
        expected_version: detail.version,
      });
      setDetail(updated);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setActionError("This integration was changed elsewhere. Reloading the latest version…");
        load();
      } else if (err instanceof ApiError) {
        setActionError(err.message);
      } else {
        setActionError("Could not save changes.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleVerify() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    setVerifyResult(null);
    try {
      const result = await verifyIntegration(tenantId, detail.id);
      setVerifyResult(result);
      load();
    } catch {
      setActionError("Could not verify this connection.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSendTestEvent() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    try {
      await sendTestEvent(tenantId, detail.id);
      setActionError(null);
    } catch {
      setActionError("Could not send a test event.");
    } finally {
      setBusy(false);
    }
  }

  async function handlePause() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    try {
      setDetail(await pauseIntegration(tenantId, detail.id, detail.version));
    } catch {
      setActionError("Could not pause this integration.");
    } finally {
      setBusy(false);
    }
  }

  async function handleResume() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    try {
      setDetail(await resumeIntegration(tenantId, detail.id, detail.version));
    } catch {
      setActionError("Could not resume this integration.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisable() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    try {
      setDetail(await disableIntegration(tenantId, detail.id, detail.version));
      setConfirming(null);
    } catch {
      setActionError("Could not disable this integration.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRotateSecret() {
    if (!detail || !newSecret) return;
    setBusy(true);
    setActionError(null);
    try {
      setDetail(await rotateSigningSecret(tenantId, detail.id, newSecret, detail.version));
      setNewSecret("");
      setConfirming(null);
    } catch {
      setActionError("Could not rotate the signing secret.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRotateInboundKey() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    try {
      const result = await generateInboundApiKey(tenantId, detail.id, detail.version);
      setOneTimeKey(result.api_key);
      setConfirming(null);
      load();
    } catch {
      setActionError("Could not generate a new inbound API key.");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!detail) return <LoadingState />;

  const availableEvents = allowedEventTypesFor(detail.connector_type);

  return (
    <div className="flex flex-col gap-6">
      <Link href="/dashboard/integrations" className="text-sm text-neutral-500">
        ← All integrations
      </Link>

      <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3 justify-between">
          <div className="flex items-center gap-3">
            <h2 className="font-medium">{detail.name}</h2>
            <StatusBadge status={detail.status} />
            <span className="text-sm text-neutral-500">{CONNECTOR_TYPE_LABELS[detail.connector_type]}</span>
          </div>
          <Link href={`/dashboard/integrations/${detail.id}/deliveries`} className="text-sm underline">
            View delivery history
          </Link>
        </div>

        <div className="grid sm:grid-cols-3 gap-3 text-sm">
          <div>
            <p className="text-xs text-neutral-500">Consecutive failures</p>
            <p>{detail.failure_count}</p>
          </div>
          <div>
            <p className="text-xs text-neutral-500">Last verified</p>
            <p>{detail.last_verified_at ? new Date(detail.last_verified_at).toLocaleString() : "Never"}</p>
          </div>
          <div>
            <p className="text-xs text-neutral-500">Last delivery</p>
            <p>
              {detail.last_delivery_at ? new Date(detail.last_delivery_at).toLocaleString() : "Never"}
              {detail.last_delivery_status && ` (${detail.last_delivery_status})`}
            </p>
          </div>
        </div>

        {canManage && (
          <div className="flex flex-wrap gap-2 pt-2 border-t border-black/5 dark:border-white/10">
            <button
              type="button"
              disabled={busy}
              onClick={handleVerify}
              className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Test connection
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleSendTestEvent}
              className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Send test event
            </button>
            {detail.status === "paused" ? (
              <button
                type="button"
                disabled={busy}
                onClick={handleResume}
                className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
              >
                Resume
              </button>
            ) : detail.status !== "disabled" ? (
              <button
                type="button"
                disabled={busy}
                onClick={handlePause}
                className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
              >
                Pause
              </button>
            ) : null}
            {detail.status !== "disabled" && (
              <button
                type="button"
                disabled={busy}
                onClick={() => setConfirming("disable")}
                className="rounded border border-red-400 dark:border-red-700 text-red-700 dark:text-red-400 px-3 py-1.5 text-sm disabled:opacity-50"
              >
                Disable
              </button>
            )}
          </div>
        )}

        {verifyResult && (
          <p
            className={`text-sm ${verifyResult.success ? "text-green-700 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}
            role="status"
          >
            {verifyResult.success ? "Connection verified successfully." : `Verification failed: ${verifyResult.error_summary}`}
          </p>
        )}
        {actionError && (
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">
            {actionError}
          </p>
        )}
      </section>

      {oneTimeKey && <OneTimeSecretPanel apiKey={oneTimeKey} onDismiss={() => setOneTimeKey(null)} />}

      {canManage && (
        <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-4">
          <h2 className="font-medium">Configuration</h2>

          {connectorRequiresDestinationUrl(detail.connector_type) && (
            <div className="flex flex-col gap-1">
              <label htmlFor="edit-destination-url" className="text-sm font-medium">
                Destination URL
              </label>
              <input
                id="edit-destination-url"
                value={destinationUrl}
                onChange={(e) => setDestinationUrl(e.target.value)}
                className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-sm font-mono"
              />
            </div>
          )}

          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium mb-1">Enabled events</legend>
            <div className="flex flex-col gap-2 rounded-lg border border-black/10 dark:border-white/10 p-3 max-h-72 overflow-y-auto">
              {availableEvents.map((eventType) => (
                <label key={eventType} className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={selectedEvents.has(eventType)} onChange={() => toggleEvent(eventType)} className="mt-0.5" />
                  <span className="flex flex-col">
                    <span className="font-mono">{eventType}</span>
                    {PII_EVENT_TYPES.has(eventType) && (
                      <span className="text-xs text-amber-700 dark:text-amber-400">Includes captured contact details.</span>
                    )}
                    {SAFETY_EVENT_TYPES.has(eventType) && (
                      <span className="text-xs text-amber-700 dark:text-amber-400">Safety classification only, for human review.</span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {connectorRequiresDestinationUrl(detail.connector_type) && (
            <MappingEditor tenantId={tenantId} connectionId={detail.id} mapping={mappingJson} onChange={setMappingJson} />
          )}

          <div>
            <button
              type="button"
              disabled={busy}
              onClick={handleSaveConfig}
              className="rounded bg-foreground text-background px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              Save changes
            </button>
          </div>
        </section>
      )}

      {canManage && connectorRequiresSigningSecret(detail.connector_type) && (
        <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-2">
          <h2 className="font-medium">Outbound signing secret</h2>
          <p className="text-sm text-neutral-500">
            {detail.has_signing_secret ? "A signing secret is configured." : "No signing secret is configured."} Never
            shown again after it is set — rotate it to replace it.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <label htmlFor="new-signing-secret" className="text-xs text-neutral-500">
                New signing secret
              </label>
              <input
                id="new-signing-secret"
                type="password"
                autoComplete="new-password"
                value={newSecret}
                onChange={(e) => setNewSecret(e.target.value)}
                className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-sm font-mono"
              />
            </div>
            <button
              type="button"
              disabled={busy || !newSecret}
              onClick={() => setConfirming("rotate-secret")}
              className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Rotate secret
            </button>
          </div>
        </section>
      )}

      {canManage && (
        <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-2">
          <h2 className="font-medium">Inbound API key</h2>
          <p className="text-sm text-neutral-500">
            Lets Revenue Brain, the future AI Sales Employee, or another authorized system push a narrow set of
            events into this platform. Only the key&apos;s prefix and last four characters are ever shown again.
          </p>
          <p className="text-sm">
            {detail.inbound_api_key_prefix
              ? `Current key: ${detail.inbound_api_key_prefix}••••••••${detail.inbound_api_key_last_four}`
              : "No inbound API key has been generated yet."}
          </p>
          <div>
            <button
              type="button"
              disabled={busy}
              onClick={() => setConfirming("rotate-inbound-key")}
              className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
            >
              {detail.inbound_api_key_prefix ? "Rotate inbound key" : "Generate inbound key"}
            </button>
          </div>
        </section>
      )}

      <ConfirmDialog
        open={confirming === "disable"}
        title="Disable this integration?"
        description="No further events will be delivered until it is resumed. Pending deliveries already queued will not be attempted while disabled."
        confirmLabel="Disable"
        destructive
        busy={busy}
        onConfirm={handleDisable}
        onCancel={() => setConfirming(null)}
      />
      <ConfirmDialog
        open={confirming === "rotate-secret"}
        title="Rotate the signing secret?"
        description="Every request signed with the old secret — outbound and inbound — will immediately start failing signature verification. Update your receiver before rotating."
        confirmLabel="Rotate secret"
        destructive
        busy={busy}
        onConfirm={handleRotateSecret}
        onCancel={() => setConfirming(null)}
      />
      <ConfirmDialog
        open={confirming === "rotate-inbound-key"}
        title={detail.inbound_api_key_prefix ? "Rotate the inbound API key?" : "Generate an inbound API key?"}
        description={
          detail.inbound_api_key_prefix
            ? "The current key will stop working immediately. Update any system using it before rotating."
            : "The new key will be shown exactly once — have somewhere ready to save it."
        }
        confirmLabel={detail.inbound_api_key_prefix ? "Rotate key" : "Generate key"}
        destructive={Boolean(detail.inbound_api_key_prefix)}
        busy={busy}
        onConfirm={handleRotateInboundKey}
        onCancel={() => setConfirming(null)}
      />
    </div>
  );
}

export default function IntegrationDetailPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Integration</h1>
      <IntegrationDetailBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
