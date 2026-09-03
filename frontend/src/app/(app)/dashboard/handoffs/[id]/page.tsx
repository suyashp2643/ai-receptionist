"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { ErrorState, LoadingState } from "@/components/dashboard/ListStates";
import { NotesPanel } from "@/components/dashboard/NotesPanel";
import { ApiError } from "@/lib/api";
import { claimHandoff, getHandoffDetail, updateHandoffStatus, type HandoffDetail } from "@/lib/dashboard-api";
import { useAuth } from "@/lib/auth-context";

function HandoffDetailBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [detail, setDetail] = useState<HandoffDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);

  function load() {
    setError(null);
    getHandoffDetail(tenantId, params.id)
      .then(setDetail)
      .catch(() => setError("Could not load this handoff."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, params.id]);

  async function handleClaim() {
    if (!detail) return;
    setUpdating(true);
    setActionError(null);
    try {
      const updated = await claimHandoff(tenantId, detail.id);
      setDetail(updated);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setActionError("Someone else already claimed this handoff. Reloading…");
        load();
      } else {
        setActionError("Could not claim this handoff.");
      }
    } finally {
      setUpdating(false);
    }
  }

  async function handleStatus(newStatus: string) {
    if (!detail) return;
    setUpdating(true);
    setActionError(null);
    try {
      const updated = await updateHandoffStatus(tenantId, detail.id, newStatus, detail.version);
      setDetail(updated);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setActionError("This handoff was changed by someone else. Reloading the latest version…");
        load();
      } else if (e instanceof ApiError) {
        setActionError(e.message);
      } else {
        setActionError("Could not update this handoff.");
      }
    } finally {
      setUpdating(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!detail) return <LoadingState />;

  return (
    <div className="flex flex-col gap-6">
      <Link href="/dashboard/handoffs" className="text-sm text-neutral-500">
        ← All handoffs
      </Link>

      {detail.is_clinic_emergency && (
        <section className="rounded-lg border border-red-400 dark:border-red-700 bg-red-50 dark:bg-red-950/30 p-4" role="alert">
          <p className="font-medium text-red-800 dark:text-red-300">
            This conversation triggered the clinic-emergency safety response. Treat with urgency — this is not an ordinary handoff.
          </p>
        </section>
      )}

      <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <StatusBadge status={detail.status} />
          {detail.urgency && <span className="text-sm text-neutral-500">Urgency: {detail.urgency}</span>}
        </div>
        <p className="text-sm whitespace-pre-wrap">{detail.reason}</p>
        <p className="text-sm text-neutral-500">Preferred contact: {detail.preferred_contact_method ?? "not specified"}</p>
        {detail.assigned_user_id && <p className="text-sm text-neutral-500">Assigned to you or a teammate.</p>}

        <div className="flex flex-wrap gap-2 mt-2">
          {detail.status === "open" && (
            <button
              type="button"
              disabled={updating}
              onClick={handleClaim}
              className="rounded bg-foreground text-background px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Claim
            </button>
          )}
          {detail.status === "claimed" && (
            <button
              type="button"
              disabled={updating}
              onClick={() => handleStatus("resolved")}
              className="rounded bg-foreground text-background px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Mark resolved
            </button>
          )}
          {canManage && (detail.status === "open" || detail.status === "claimed") && (
            <button
              type="button"
              disabled={updating}
              onClick={() => handleStatus("cancelled")}
              className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Cancel
            </button>
          )}
        </div>
        <p className="text-xs text-neutral-500 mt-2">No automatic notification is sent to the visitor for any of these actions.</p>
      </section>
      {actionError && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{actionError}</p>}

      <Link href={`/dashboard/conversations/${detail.conversation_id}`} className="rounded-lg border border-black/10 dark:border-white/10 p-4 underline text-sm w-fit">
        View linked transcript
      </Link>

      {user && <NotesPanel tenantId={tenantId} entityType="human_handoff" entityId={detail.id} currentUserId={user.id} />}
    </div>
  );
}

export default function HandoffDetailPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Handoff</h1>
      <HandoffDetailBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
