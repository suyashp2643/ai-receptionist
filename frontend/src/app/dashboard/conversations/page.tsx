"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { SourceBadge, StatusBadge } from "@/components/dashboard/StatusBadge";
import { EmptyState, ErrorState, LoadingState, PaginationControls } from "@/components/dashboard/ListStates";
import { ExportButton } from "@/components/dashboard/ExportButton";
import { DateRangeFilter, defaultDateRange } from "@/components/dashboard/DateRangeFilter";
import { listConversations, type ConversationListItem, type ConversationSource } from "@/lib/dashboard-api";

const LIMIT = 25;

function ConversationsBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const [items, setItems] = useState<ConversationListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<ConversationSource | "">("");
  const [safetyOnly, setSafetyOnly] = useState(false);
  const [{ dateFrom, dateTo }, setDateRange] = useState(defaultDateRange());
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    listConversations(tenantId, {
      limit: LIMIT,
      offset,
      search: search || undefined,
      source: sourceFilter ? [sourceFilter] : undefined,
      onlySafetyEvents: safetyOnly,
      sortDirection: "desc",
      dateFrom,
      dateTo,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Could not load conversations."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, offset, sourceFilter, safetyOnly, dateFrom, dateTo]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="conv-search" className="text-xs text-neutral-500">
              Search visitor / contact
            </label>
            <input
              id="conv-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setOffset(0);
                  load();
                }
              }}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
              placeholder="name, email, phone…"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="conv-source" className="text-xs text-neutral-500">
              Source
            </label>
            <select
              id="conv-source"
              value={sourceFilter}
              onChange={(e) => {
                setOffset(0);
                setSourceFilter(e.target.value as ConversationSource | "");
              }}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
            >
              <option value="">All sources</option>
              <option value="widget">Widget</option>
              <option value="preview">Preview</option>
              <option value="test">Test</option>
            </select>
          </div>
          <DateRangeFilter
            idPrefix="conv"
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
          <label className="flex items-center gap-2 text-sm pb-1.5">
            <input
              type="checkbox"
              checked={safetyOnly}
              onChange={(e) => {
                setOffset(0);
                setSafetyOnly(e.target.checked);
              }}
            />
            Safety events only
          </label>
        </div>
        <ExportButton
          tenantId={tenantId}
          entity="conversations"
          canManage={canManage}
          dateFrom={dateFrom}
          dateTo={dateTo}
          sources={sourceFilter ? [sourceFilter] : undefined}
        />
      </div>

      {error && <ErrorState message={error} onRetry={load} />}

      {!items ? (
        <LoadingState />
      ) : items.length === 0 ? (
        <EmptyState title="No conversations found" hint="Try widening your filters, or share your widget to start collecting real conversations." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-black/5 dark:bg-white/5 text-left">
              <tr>
                <th className="px-3 py-2">Started</th>
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Qualification</th>
                <th className="px-3 py-2">Safety</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-t border-black/5 dark:border-white/10 hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                  <td className="px-3 py-2">
                    <Link href={`/dashboard/conversations/${c.id}`} className="underline">
                      {new Date(c.started_at).toLocaleString()}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <SourceBadge source={c.source} />
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-3 py-2">{c.qualification_complete ? "Complete" : "Incomplete"}</td>
                  <td className="px-3 py-2">
                    {c.had_clinic_emergency ? (
                      <span className="text-red-600 dark:text-red-400 font-medium">Clinic emergency</span>
                    ) : c.had_safety_event ? (
                      <span className="text-amber-600 dark:text-amber-400">Safety event</span>
                    ) : (
                      "—"
                    )}
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

export default function ConversationsPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Conversations</h1>
      <ConversationsBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
