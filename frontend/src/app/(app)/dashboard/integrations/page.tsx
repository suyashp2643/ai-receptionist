"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/dashboard/ListStates";
import {
  CONNECTOR_TYPE_LABELS,
  CONNECTOR_TYPES,
  getIntegrationHealth,
  listIntegrations,
  type ConnectorType,
  type IntegrationConnection,
  type TenantIntegrationHealth,
} from "@/lib/integrations-api";

const STATUSES = ["configured", "verified", "paused", "failing", "disabled"];

function formatRelative(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}

function HealthSummaryBar({ health }: { health: TenantIntegrationHealth }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg border border-black/10 dark:border-white/10 p-3">
          <p className="text-xs text-neutral-500">Active</p>
          <p className="text-xl font-semibold">{health.connections.active}</p>
        </div>
        <div className="rounded-lg border border-black/10 dark:border-white/10 p-3">
          <p className="text-xs text-neutral-500">Failing</p>
          <p className="text-xl font-semibold">{health.connections.failing}</p>
        </div>
        <div className="rounded-lg border border-black/10 dark:border-white/10 p-3">
          <p className="text-xs text-neutral-500">Pending events</p>
          <p className="text-xl font-semibold">{health.pending_events}</p>
        </div>
        <div className="rounded-lg border border-black/10 dark:border-white/10 p-3">
          <p className="text-xs text-neutral-500">Dead-lettered</p>
          <p className="text-xl font-semibold">{health.dead_letter_count}</p>
        </div>
      </div>
      {health.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-3 flex flex-col gap-1" role="status">
          {health.warnings.map((w, i) => (
            <p key={i} className="text-sm text-amber-800 dark:text-amber-300">
              {w.message}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function IntegrationsBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const [items, setItems] = useState<IntegrationConnection[] | null>(null);
  const [health, setHealth] = useState<TenantIntegrationHealth | null>(null);
  const [connectorFilter, setConnectorFilter] = useState<ConnectorType | "">("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    Promise.all([listIntegrations(tenantId), getIntegrationHealth(tenantId)])
      .then(([listRes, healthRes]) => {
        setItems(listRes.items);
        setHealth(healthRes);
      })
      .catch(() => setError("Could not load integrations."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  const filtered = (items ?? []).filter(
    (item) =>
      (!connectorFilter || item.connector_type === connectorFilter) && (!statusFilter || item.status === statusFilter)
  );

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-neutral-500">
        Connects this receptionist to Revenue Brain, the future AI Sales Employee, and any other webhook receiver.
        Read more in the{" "}
        <Link href="/dashboard/integrations/lab" className="underline">
          integration lab
        </Link>
        .
      </p>

      {error && <ErrorState message={error} onRetry={load} />}
      {health && <HealthSummaryBar health={health} />}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="connector-filter" className="text-xs text-neutral-500">
              Connector type
            </label>
            <select
              id="connector-filter"
              value={connectorFilter}
              onChange={(e) => setConnectorFilter(e.target.value as ConnectorType | "")}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
            >
              <option value="">All types</option>
              {CONNECTOR_TYPES.map((t) => (
                <option key={t} value={t}>
                  {CONNECTOR_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="status-filter" className="text-xs text-neutral-500">
              Status
            </label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
            >
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>
        {canManage && (
          <Link
            href="/dashboard/integrations/new"
            className="rounded bg-foreground text-background px-3 py-1.5 text-sm font-medium"
          >
            New integration
          </Link>
        )}
      </div>

      {!items ? (
        <LoadingState />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No integrations found"
          hint={
            canManage
              ? "Create a connection to send events to Revenue Brain, an AI Sales Employee, or your own webhook receiver."
              : "An owner or admin has not configured any integrations yet."
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-black/5 dark:bg-white/5 text-left">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Consecutive failures</th>
                <th className="px-3 py-2">Last delivery</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr
                  key={item.id}
                  className="border-t border-black/5 dark:border-white/10 hover:bg-black/[0.02] dark:hover:bg-white/[0.03]"
                >
                  <td className="px-3 py-2">
                    <Link href={`/dashboard/integrations/${item.id}`} className="underline">
                      {item.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{CONNECTOR_TYPE_LABELS[item.connector_type]}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-3 py-2">{item.failure_count}</td>
                  <td className="px-3 py-2">
                    {formatRelative(item.last_delivery_at)}
                    {item.last_delivery_status && (
                      <span className="ml-2 text-xs text-neutral-500">({item.last_delivery_status})</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function IntegrationsPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Integrations</h1>
      <IntegrationsBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
