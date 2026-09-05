"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { EmptyState, ErrorState, LoadingState, PaginationControls } from "@/components/dashboard/ListStates";
import { ApiError } from "@/lib/api";
import { listDeliveries, replayDelivery, type IntegrationOutboxEventItem } from "@/lib/integrations-api";

const LIMIT = 25;

function DeliveriesBody({ tenantId, canManage, connectionId }: { tenantId: string; canManage: boolean; connectionId: string }) {
  const [items, setItems] = useState<IntegrationOutboxEventItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [replayingId, setReplayingId] = useState<string | null>(null);

  function load() {
    setError(null);
    listDeliveries(tenantId, connectionId, { limit: LIMIT, offset })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Could not load delivery history."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, connectionId, offset]);

  async function handleReplay(eventId: string) {
    setReplayingId(eventId);
    setReplayError(null);
    try {
      await replayDelivery(tenantId, connectionId, eventId);
      load();
    } catch (err) {
      if (err instanceof ApiError) setReplayError(err.message);
      else setReplayError("Could not replay this delivery.");
    } finally {
      setReplayingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Link href={`/dashboard/integrations/${connectionId}`} className="text-sm text-neutral-500">
        ← Back to integration
      </Link>

      {error && <ErrorState message={error} onRetry={load} />}
      {replayError && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {replayError}
        </p>
      )}

      {!items ? (
        <LoadingState />
      ) : items.length === 0 ? (
        <EmptyState title="No deliveries yet" hint="Events will appear here once this connection is subscribed to at least one event type." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-black/5 dark:bg-white/5 text-left">
              <tr>
                <th className="px-3 py-2">Event type</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Attempts</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2">Delivered / dead-lettered</th>
                <th className="px-3 py-2">Last error</th>
                {canManage && <th className="px-3 py-2">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-black/5 dark:border-white/10">
                  <td className="px-3 py-2 font-mono text-xs">{item.event_type}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-3 py-2">{item.attempt_count}</td>
                  <td className="px-3 py-2">{new Date(item.created_at).toLocaleString()}</td>
                  <td className="px-3 py-2">
                    {item.delivered_at
                      ? new Date(item.delivered_at).toLocaleString()
                      : item.dead_lettered_at
                        ? new Date(item.dead_lettered_at).toLocaleString()
                        : "—"}
                  </td>
                  <td className="px-3 py-2 max-w-xs truncate text-neutral-500">{item.last_error ?? "—"}</td>
                  {canManage && (
                    <td className="px-3 py-2">
                      {item.status === "dead_letter" && (
                        <button
                          type="button"
                          disabled={replayingId === item.id}
                          onClick={() => handleReplay(item.id)}
                          className="rounded border border-black/15 dark:border-white/20 px-2 py-1 text-xs disabled:opacity-50"
                        >
                          {replayingId === item.id ? "Replaying…" : "Replay"}
                        </button>
                      )}
                    </td>
                  )}
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

export default function IntegrationDeliveriesPage() {
  const { tenantId, canManage } = useDashboardContext();
  const params = useParams<{ id: string }>();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Delivery history</h1>
      <DeliveriesBody tenantId={tenantId} canManage={canManage} connectionId={params.id} />
    </>
  );
}
