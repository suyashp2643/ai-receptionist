"use client";

import { useEffect, useState } from "react";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { EmptyState, ErrorState, LoadingState, PaginationControls } from "@/components/dashboard/ListStates";
import { listActivity, type ActivityEvent } from "@/lib/dashboard-api";

const LIMIT = 25;

const ACTION_LABEL: Record<string, string> = {
  "enquiry.status_changed": "Enquiry status changed",
  "appointment_request.status_changed": "Appointment status changed",
  "handoff.claimed": "Handoff claimed",
  "handoff.resolved": "Handoff resolved",
  "handoff.cancelled": "Handoff cancelled",
  "note.created": "Note added",
  "note.deleted": "Note deleted",
  "export.downloaded": "Data exported",
};

function ActivityBody({ tenantId }: { tenantId: string }) {
  const [items, setItems] = useState<ActivityEvent[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    listActivity(tenantId, { limit: LIMIT, offset })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Could not load recent activity."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, offset]);

  return (
    <div className="flex flex-col gap-4">
      {error && <ErrorState message={error} onRetry={load} />}
      {!items ? (
        <LoadingState />
      ) : items.length === 0 ? (
        <EmptyState title="No activity yet" hint="Status changes, claims, and notes will appear here as your team works." />
      ) : (
        <ol className="flex flex-col gap-2">
          {items.map((event) => (
            <li key={event.id} className="rounded-lg border border-black/10 dark:border-white/10 p-3 flex items-start justify-between gap-4">
              <div>
                <p className="font-medium text-sm">{ACTION_LABEL[event.action_type] ?? event.action_type}</p>
                {typeof event.event_metadata.from === "string" && typeof event.event_metadata.to === "string" && (
                  <p className="text-xs text-neutral-500">
                    {event.event_metadata.from} → {event.event_metadata.to}
                  </p>
                )}
              </div>
              <span className="text-xs text-neutral-400 shrink-0">{new Date(event.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ol>
      )}
      <PaginationControls total={total} limit={LIMIT} offset={offset} onOffsetChange={setOffset} />
    </div>
  );
}

export default function ActivityPage() {
  const { tenantId } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Recent activity</h1>
      <ActivityBody tenantId={tenantId} />
    </>
  );
}
