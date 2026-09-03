"use client";

import { useEffect, useState } from "react";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { listLocations, listReceptionists, listServices, type Receptionist } from "@/lib/phase3-api";
import {
  activateWidgetInstallation,
  createWidgetInstallation,
  getWidgetEmbedSnippet,
  listWidgetAppointmentRequests,
  listWidgetContacts,
  listWidgetEnquiries,
  listWidgetHandoffRequests,
  listWidgetInstallations,
  pauseWidgetInstallation,
  revokeWidgetInstallation,
  updateWidgetInstallation,
  type WidgetAppointmentRequestRecord,
  type WidgetContactRecord,
  type WidgetEmbedSnippet,
  type WidgetEnquiryRecord,
  type WidgetHandoffRecord,
  type WidgetInstallation,
} from "@/lib/widget-installations-api";
import { buttonClass, errorMessage, inputClass, secondaryButtonClass, dangerButtonClass } from "@/components/settings/shared";
import { getApiBaseUrl } from "@/lib/config";

export default function WidgetInstallationPage() {
  const { tenantId, canManage } = useDashboardContext();

  const [receptionists, setReceptionists] = useState<Receptionist[]>([]);
  const [selectedReceptionistId, setSelectedReceptionistId] = useState("");
  const [installations, setInstallations] = useState<WidgetInstallation[]>([]);
  const [selectedInstallation, setSelectedInstallation] = useState<WidgetInstallation | null>(null);
  const [snippet, setSnippet] = useState<WidgetEmbedSnippet | null>(null);
  const [domainsInput, setDomainsInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [contacts, setContacts] = useState<WidgetContactRecord[]>([]);
  const [enquiries, setEnquiries] = useState<WidgetEnquiryRecord[]>([]);
  const [appointments, setAppointments] = useState<WidgetAppointmentRequestRecord[]>([]);
  const [handoffs, setHandoffs] = useState<WidgetHandoffRecord[]>([]);
  const [serviceNames, setServiceNames] = useState<Record<string, string>>({});
  const [locationNames, setLocationNames] = useState<Record<string, string>>({});

  useEffect(() => {
    listReceptionists(tenantId)
      .then((list) => {
        setReceptionists(list);
        if (list.length > 0) setSelectedReceptionistId((current) => current || list[0].id);
      })
      .catch((err) => setError(errorMessage(err)));
  }, [tenantId]);

  function refreshInstallations() {
    if (!tenantId) return;
    listWidgetInstallations(tenantId)
      .then(setInstallations)
      .catch((err) => setError(errorMessage(err)));
  }

  useEffect(refreshInstallations, [tenantId]);

  function refreshRecords() {
    if (!tenantId) return;
    listWidgetContacts(tenantId).then(setContacts).catch(() => setContacts([]));
    listWidgetEnquiries(tenantId).then(setEnquiries).catch(() => setEnquiries([]));
    listWidgetAppointmentRequests(tenantId).then(setAppointments).catch(() => setAppointments([]));
    listWidgetHandoffRequests(tenantId).then(setHandoffs).catch(() => setHandoffs([]));
  }

  useEffect(refreshRecords, [tenantId]);

  useEffect(() => {
    if (!tenantId) return;
    listServices(tenantId)
      .then((services) => setServiceNames(Object.fromEntries(services.map((s) => [s.id, s.name]))))
      .catch(() => setServiceNames({}));
    listLocations(tenantId)
      .then((locations) => setLocationNames(Object.fromEntries(locations.map((l) => [l.id, l.name]))))
      .catch(() => setLocationNames({}));
  }, [tenantId]);

  useEffect(() => {
    if (!tenantId || !selectedInstallation) {
      setSnippet(null);
      return;
    }
    getWidgetEmbedSnippet(tenantId, selectedInstallation.id)
      .then(setSnippet)
      .catch((err) => setError(errorMessage(err)));
  }, [tenantId, selectedInstallation]);

  async function handleCreate() {
    if (!tenantId || !selectedReceptionistId) return;
    setError(null);
    try {
      const created = await createWidgetInstallation(tenantId, { receptionist_id: selectedReceptionistId });
      refreshInstallations();
      setSelectedInstallation(created);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleSaveDomains() {
    if (!tenantId || !selectedInstallation) return;
    setError(null);
    const domains = domainsInput
      .split(",")
      .map((d) => d.trim())
      .filter(Boolean);
    try {
      const updated = await updateWidgetInstallation(tenantId, selectedInstallation.id, { allowed_domains: domains });
      setSelectedInstallation(updated);
      refreshInstallations();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleStatusChange(action: "activate" | "pause" | "revoke") {
    if (!tenantId || !selectedInstallation) return;
    setError(null);
    try {
      const fn =
        action === "activate" ? activateWidgetInstallation : action === "pause" ? pauseWidgetInstallation : revokeWidgetInstallation;
      const updated = await fn(tenantId, selectedInstallation.id);
      setSelectedInstallation(updated);
      refreshInstallations();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function handleCopySnippet() {
    if (!snippet) return;
    navigator.clipboard?.writeText(snippet.embed_snippet).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="max-w-4xl mx-auto w-full flex flex-col gap-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight">Website widget</h1>
          <span
            className="rounded-full bg-amber-100 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 px-3 py-1 text-xs font-medium"
            title="The embeddable widget runs the same deterministic, zero-cost demonstration engine as the test console."
          >
            Mock AI demonstration
          </span>
        </header>

        {error && (
          <p role="alert" className="rounded border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/30 p-3 text-sm text-red-700 dark:text-red-400">
            {error}
          </p>
        )}

        <section className="rounded-lg border border-black/10 dark:border-white/15 p-4 flex flex-col gap-3">
          <h2 className="font-medium text-sm">Create an installation</h2>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Receptionist
              <select
                className={inputClass}
                value={selectedReceptionistId}
                onChange={(e) => setSelectedReceptionistId(e.target.value)}
              >
                {receptionists.length === 0 && <option value="">No receptionists yet</option>}
                {receptionists.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className={buttonClass} onClick={handleCreate} disabled={!canManage || !selectedReceptionistId}>
              Create widget installation
            </button>
          </div>
          {!canManage && <p className="text-xs text-neutral-500">Only owners and admins can create or modify installations.</p>}
        </section>

        <section className="rounded-lg border border-black/10 dark:border-white/15 p-4 flex flex-col gap-3">
          <h2 className="font-medium text-sm">Installations</h2>
          {installations.length === 0 ? (
            <p className="text-sm text-neutral-500">No widget installations yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {installations.map((inst) => (
                <li key={inst.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedInstallation(inst);
                      setDomainsInput(inst.allowed_domains.join(", "));
                    }}
                    className={`w-full text-left rounded border px-3 py-2 text-sm ${
                      selectedInstallation?.id === inst.id ? "border-foreground" : "border-black/10 dark:border-white/15"
                    }`}
                  >
                    <span className="font-mono text-xs">{inst.public_id}</span>{" "}
                    <StatusBadge status={inst.status} />
                    <span className="block text-xs text-neutral-500 mt-1">
                      {inst.allowed_domains.length > 0 ? inst.allowed_domains.join(", ") : "No allowed domains configured yet"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {selectedInstallation && (
          <section className="rounded-lg border border-black/10 dark:border-white/15 p-4 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="font-medium text-sm">
                Manage installation <StatusBadge status={selectedInstallation.status} />
              </h2>
              {canManage && selectedInstallation.status !== "revoked" && (
                <div className="flex gap-2">
                  {selectedInstallation.status !== "active" && (
                    <button type="button" className={secondaryButtonClass} onClick={() => handleStatusChange("activate")}>
                      Activate
                    </button>
                  )}
                  {selectedInstallation.status === "active" && (
                    <button type="button" className={secondaryButtonClass} onClick={() => handleStatusChange("pause")}>
                      Pause
                    </button>
                  )}
                  <button type="button" className={dangerButtonClass} onClick={() => handleStatusChange("revoke")}>
                    Revoke
                  </button>
                </div>
              )}
            </div>

            <label className="flex flex-col gap-1 text-sm">
              Allowed domains (comma-separated, e.g. example.com, www.example.com)
              <input
                className={inputClass}
                value={domainsInput}
                onChange={(e) => setDomainsInput(e.target.value)}
                disabled={!canManage}
                placeholder="example.com"
              />
            </label>
            <button
              type="button"
              className={secondaryButtonClass}
              onClick={handleSaveDomains}
              disabled={!canManage}
              style={{ alignSelf: "flex-start" }}
            >
              Save allowed domains
            </button>

            {snippet && (
              <div className="flex flex-col gap-2">
                <h3 className="font-medium text-sm">Installation snippet</h3>
                <p className="text-xs text-neutral-500">
                  Paste this before <code>&lt;/body&gt;</code> on any page served from an allowed domain. It contains no
                  secret and no internal tenant identifier — only the widget&apos;s public, revocable identifier.
                </p>
                <pre className="rounded bg-black/5 dark:bg-white/10 p-3 text-xs overflow-x-auto">{snippet.embed_snippet}</pre>
                <button type="button" className={secondaryButtonClass} onClick={handleCopySnippet} style={{ alignSelf: "flex-start" }}>
                  {copied ? "Copied!" : "Copy snippet"}
                </button>
              </div>
            )}

            <WidgetLivePreview installation={selectedInstallation} snippet={snippet} />
          </section>
        )}

        <RecordsSection
          contacts={contacts}
          enquiries={enquiries}
          appointments={appointments}
          handoffs={handoffs}
          serviceNames={serviceNames}
          locationNames={locationNames}
        />
    </div>
  );
}

function StatusBadge({ status }: { status: WidgetInstallation["status"] }) {
  const colorClass =
    status === "active"
      ? "bg-green-100 dark:bg-green-950/40 text-green-800 dark:text-green-300"
      : status === "paused"
        ? "bg-amber-100 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300"
        : status === "revoked"
          ? "bg-red-100 dark:bg-red-950/40 text-red-800 dark:text-red-300"
          : "bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300";
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}>{status}</span>;
}

function newPreviewSessionNamespace(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `preview-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function WidgetLivePreview({
  installation,
  snippet,
}: {
  installation: WidgetInstallation;
  snippet: WidgetEmbedSnippet | null;
}) {
  const [sessionNamespace, setSessionNamespace] = useState(() => newPreviewSessionNamespace());

  if (installation.status !== "active") {
    return (
      <div className="flex flex-col gap-2">
        <h3 className="font-medium text-sm">Live local preview</h3>
        <p className="text-xs text-neutral-500">
          Activate this installation to preview it live — a {installation.status} installation cannot start a
          conversation.
        </p>
      </div>
    );
  }

  if (!snippet) {
    return null;
  }

  const previewUrl = `/widget-preview.html?${new URLSearchParams({
    publicId: installation.public_id,
    apiBaseUrl: getApiBaseUrl(),
    bundleUrl: snippet.widget_bundle_url,
    sessionNamespace,
  }).toString()}`;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-sm">Live local preview</h3>
        <span className="text-xs rounded-full bg-amber-100 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 px-2 py-0.5 font-medium">
          Live local preview — Mock AI
        </span>
      </div>
      <p className="text-xs text-neutral-500">
        This loads the real widget bundle against the real public API, using a visitor capability token exactly like
        a real embed — it never reuses your dashboard sign-in. Preview conversations are tagged separately from real
        visitor traffic in your records.
      </p>
      <div className="rounded-lg border border-black/10 dark:border-white/15 overflow-hidden max-w-sm bg-background">
        <iframe
          key={sessionNamespace}
          src={previewUrl}
          title="Live local widget preview"
          sandbox="allow-scripts allow-same-origin allow-forms"
          style={{ width: "100%", height: 520, border: "none", display: "block" }}
        />
      </div>
      <button
        type="button"
        className={secondaryButtonClass}
        onClick={() => setSessionNamespace(newPreviewSessionNamespace())}
        style={{ alignSelf: "flex-start" }}
      >
        Restart preview
      </button>
    </div>
  );
}

function RecordsSection({
  contacts,
  enquiries,
  appointments,
  handoffs,
  serviceNames,
  locationNames,
}: {
  contacts: WidgetContactRecord[];
  enquiries: WidgetEnquiryRecord[];
  appointments: WidgetAppointmentRequestRecord[];
  handoffs: WidgetHandoffRecord[];
  serviceNames: Record<string, string>;
  locationNames: Record<string, string>;
}) {
  return (
    <section className="rounded-lg border border-black/10 dark:border-white/15 p-4 flex flex-col gap-4">
      <h2 className="font-medium text-sm">Captured widget records</h2>
      <p className="text-xs text-neutral-500">
        A minimal verification view of what visitors have submitted through the widget — full analytics arrive in a
        later phase.
      </p>

      <RecordsTable
        title="Contacts"
        rows={contacts}
        empty="No contacts captured yet."
        columns={["Name", "Email", "Phone", "Marketing consent", "Captured"]}
        render={(c) => [
          c.name ?? "—",
          c.normalized_email ?? "—",
          c.normalized_phone ?? "—",
          c.marketing_consent ? "Yes" : "No",
          new Date(c.created_at).toLocaleString(),
        ]}
      />
      <RecordsTable
        title="Enquiries"
        rows={enquiries}
        empty="No enquiries yet."
        columns={["Status", "Qualification complete", "Recommended next action", "Captured"]}
        render={(e) => [e.status, e.qualification_complete ? "Yes" : "No", e.recommended_next_action ?? "—", new Date(e.created_at).toLocaleString()]}
      />
      <RecordsTable
        title="Appointment requests"
        rows={appointments}
        empty="No appointment requests yet."
        columns={["Date", "Time", "Service", "Location", "Status", "Captured"]}
        render={(a) => [
          a.requested_date,
          a.requested_time ?? a.requested_time_window ?? "—",
          (a.service_id && serviceNames[a.service_id]) || (a.service_id ? "Unknown service" : "Not specified"),
          (a.location_id && locationNames[a.location_id]) || (a.location_id ? "Unknown location" : "Not specified"),
          a.status,
          new Date(a.created_at).toLocaleString(),
        ]}
      />
      <RecordsTable
        title="Handoff requests"
        rows={handoffs}
        empty="No handoff requests yet."
        columns={["Reason", "Status", "Captured"]}
        render={(h) => [h.reason, h.status, new Date(h.created_at).toLocaleString()]}
      />
    </section>
  );
}

function RecordsTable<T>({
  title,
  rows,
  empty,
  columns,
  render,
}: {
  title: string;
  rows: T[];
  empty: string;
  columns: string[];
  render: (row: T) => (string | number)[];
}) {
  return (
    <div>
      <h3 className="font-medium text-xs uppercase tracking-wide text-neutral-500 mb-2">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-xs text-neutral-500">{empty}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-neutral-500">
                {columns.map((c) => (
                  <th key={c} className="pr-4 pb-1 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-t border-black/5 dark:border-white/10">
                  {render(row).map((cell, j) => (
                    <td key={j} className="pr-4 py-1 truncate max-w-[200px]">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
