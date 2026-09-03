"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { EmptyState, ErrorState, LoadingState, PaginationControls } from "@/components/dashboard/ListStates";
import { ExportButton } from "@/components/dashboard/ExportButton";
import { DateRangeFilter, defaultDateRange } from "@/components/dashboard/DateRangeFilter";
import { ENQUIRY_STATUSES, listEnquiries, type EnquiryListItem } from "@/lib/dashboard-api";

const LIMIT = 25;

function EnquiriesBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const [items, setItems] = useState<EnquiryListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [{ dateFrom, dateTo }, setDateRange] = useState(defaultDateRange());
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    listEnquiries(tenantId, {
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
      .catch(() => setError("Could not load enquiries."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, offset, statusFilter, dateFrom, dateTo]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1 max-w-xs">
            <label htmlFor="enquiry-status" className="text-xs text-neutral-500">
              Status
            </label>
            <select
              id="enquiry-status"
              value={statusFilter}
              onChange={(e) => {
                setOffset(0);
                setStatusFilter(e.target.value);
              }}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
            >
              <option value="">All statuses</option>
              {ENQUIRY_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <DateRangeFilter
            idPrefix="enquiry"
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
          entity="enquiries"
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
        <EmptyState title="No enquiries found" hint="Enquiries are captured automatically as visitors qualify through the widget." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-black/5 dark:bg-white/5 text-left">
              <tr>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Qualification</th>
                <th className="px-3 py-2">Next action</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2">Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} className="border-t border-black/5 dark:border-white/10 hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                  <td className="px-3 py-2">
                    <Link href={`/dashboard/enquiries/${e.id}`} className="underline">
                      <StatusBadge status={e.status} />
                    </Link>
                  </td>
                  <td className="px-3 py-2">{e.qualification_complete ? "Complete" : "Incomplete"}</td>
                  <td className="px-3 py-2">{e.recommended_next_action ?? "—"}</td>
                  <td className="px-3 py-2">{new Date(e.created_at).toLocaleDateString()}</td>
                  <td className="px-3 py-2">{new Date(e.updated_at).toLocaleDateString()}</td>
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

export default function EnquiriesPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Enquiries</h1>
      <EnquiriesBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
