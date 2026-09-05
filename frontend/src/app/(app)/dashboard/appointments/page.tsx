"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { EmptyState, ErrorState, LoadingState, PaginationControls } from "@/components/dashboard/ListStates";
import { ExportButton } from "@/components/dashboard/ExportButton";
import { DateRangeFilter, defaultAppointmentDateRange } from "@/components/dashboard/DateRangeFilter";
import { listAppointments, type AppointmentListItem } from "@/lib/dashboard-api";

const LIMIT = 25;
const STATUSES = ["pending", "confirmed", "declined", "cancelled"];

function AppointmentsBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const [items, setItems] = useState<AppointmentListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [{ dateFrom, dateTo }, setDateRange] = useState(defaultAppointmentDateRange());
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    listAppointments(tenantId, {
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
      .catch(() => setError("Could not load appointment requests."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, offset, statusFilter, dateFrom, dateTo]);

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-neutral-500">
        Changing an appointment&rsquo;s status here never sends a message to the visitor — there is no automatic
        notification.
      </p>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1 max-w-xs">
            <label htmlFor="appt-status" className="text-xs text-neutral-500">
              Status
            </label>
            <select
              id="appt-status"
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
            idPrefix="appt"
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
          entity="appointments"
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
        <EmptyState title="No appointment requests found" hint="Visitors can request an appointment through your widget." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-black/5 dark:bg-white/5 text-left">
              <tr>
                <th className="px-3 py-2">Requested date</th>
                <th className="px-3 py-2">Time / window</th>
                <th className="px-3 py-2">Timezone</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className="border-t border-black/5 dark:border-white/10 hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                  <td className="px-3 py-2">
                    <Link href={`/dashboard/appointments/${a.id}`} className="underline">
                      {a.requested_date}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{a.requested_time ?? a.requested_time_window ?? "—"}</td>
                  <td className="px-3 py-2">{a.timezone}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={a.status} />
                  </td>
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

export default function AppointmentsPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Appointments</h1>
      <AppointmentsBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
