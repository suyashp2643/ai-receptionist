"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { EmptyState, ErrorState, LoadingState, PaginationControls } from "@/components/dashboard/ListStates";
import { ExportButton } from "@/components/dashboard/ExportButton";
import { DateRangeFilter, defaultDateRange } from "@/components/dashboard/DateRangeFilter";
import { listContacts, type ContactListItem } from "@/lib/dashboard-api";

const LIMIT = 25;

function ContactsBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const [items, setItems] = useState<ContactListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [{ dateFrom, dateTo }, setDateRange] = useState(defaultDateRange());
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    listContacts(tenantId, { limit: LIMIT, offset, search: search || undefined, dateFrom, dateTo })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Could not load contacts."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, offset, dateFrom, dateTo]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1 max-w-xs">
            <label htmlFor="contact-search" className="text-xs text-neutral-500">
              Search
            </label>
            <input
              id="contact-search"
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
          <DateRangeFilter
            idPrefix="contacts"
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
        <ExportButton tenantId={tenantId} entity="contacts" canManage={canManage} dateFrom={dateFrom} dateTo={dateTo} />
      </div>

      {error && <ErrorState message={error} onRetry={load} />}

      {!items ? (
        <LoadingState />
      ) : items.length === 0 ? (
        <EmptyState title="No contacts yet" hint="Contacts appear here once a visitor shares their details in the widget." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-black/5 dark:bg-white/5 text-left">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Phone</th>
                <th className="px-3 py-2">Consent</th>
                <th className="px-3 py-2">First seen</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-t border-black/5 dark:border-white/10 hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                  <td className="px-3 py-2">
                    <Link href={`/dashboard/contacts/${c.id}`} className="underline">
                      {c.name ?? "(no name)"}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{c.normalized_email ?? "—"}</td>
                  <td className="px-3 py-2">{c.normalized_phone ?? "—"}</td>
                  <td className="px-3 py-2">{c.marketing_consent ? "Opted in" : "Not given"}</td>
                  <td className="px-3 py-2">{new Date(c.created_at).toLocaleDateString()}</td>
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

export default function ContactsPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Contacts</h1>
      <ContactsBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
