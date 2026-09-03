"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { EmptyState, ErrorState, LoadingState, PaginationControls } from "@/components/dashboard/ListStates";
import { ExportButton } from "@/components/dashboard/ExportButton";
import { DateRangeFilter, defaultDateRange } from "@/components/dashboard/DateRangeFilter";
import { listHandoffs, type HandoffListItem } from "@/lib/dashboard-api";

const LIMIT = 25;
const STATUSES = ["open", "claimed", "resolved", "cancelled"];

function HandoffsBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const [items, setItems] = useState<HandoffListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [{ dateFrom, dateTo }, setDateRange] = useState(defaultDateRange());
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    listHandoffs(tenantId, {
      limit: LIMIT,
      offset,
      status: statusFilter ? [statusFilter] : undefined,
      dateFrom,
      dateTo,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Could not load handoff requests."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, offset, statusFilter, dateFrom, dateTo]);

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-neutral-500">Claiming or resolving a handoff here does not notify the visitor automatically.</p>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1 max-w-xs">
            <label htmlFor="handoff-status" className="text-xs text-neutral-500">
              Status
            </label>
            <select
              id="handoff-status"
              value={statusFilter}
              onChange={(e) => {
                setOffset(0);
                setStatusFilter(e.target.value);
              }}
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
          <DateRangeFilter
            idPrefix="handoff"
            dateFrom={dateFrom}
            dateTo={dateTo}
            onDateFromChange={(v) => {
              setOffset(0);
              setDateRange((r) => ({ ...r, dateFrom: v }));
            }}
            onDateToChange={(v) => {
              setOffset(0);
              setDateRange((r) => ({ ...r, dateTo: v }));
            }}
          />
        </div>
        <ExportButton
          tenantId={tenantId}
          entity="handoffs"
          canManage={canManage}
          dateFrom={dateFrom}
          dateTo={dateTo}
          statuses={statusFilter ? [statusFilter] : undefined}
        />
      </div>

      {error && <ErrorState message={error} onRetry={load} />}

      {!items ? (
        <LoadingState />
      ) : items.length === 0 ? (
        <EmptyState title="No handoff requests found" hint="Visitors can request to talk to a human through your widget." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-black/5 dark:bg-white/5 text-left">
              <tr>
                <th className="px-3 py-2">Reason</th>
                <th className="px-3 py-2">Urgency</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((h) => (
                <tr key={h.id} className="border-t border-black/5 dark:border-white/10 hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                  <td className="px-3 py-2 max-w-sm truncate">
                    <Link href={`/dashboard/handoffs/${h.id}`} className="underline">
                      {h.reason}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{h.urgency ?? "—"}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={h.status} />
                  </td>
                  <td className="px-3 py-2">{new Date(h.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <PaginationControls total={total} limit={LIMIT} offset={offset} onOffsetChange={setOffset} />
    </div>
  );
}

export default function HandoffsPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Handoffs</h1>
      <HandoffsBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
