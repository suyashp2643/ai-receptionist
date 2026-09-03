"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { ErrorState, LoadingState } from "@/components/dashboard/ListStates";
import { NotesPanel } from "@/components/dashboard/NotesPanel";
import { ApiError } from "@/lib/api";
import { getAppointmentDetail, updateAppointmentStatus, type AppointmentDetail } from "@/lib/dashboard-api";
import { useAuth } from "@/lib/auth-context";

const NEXT_STATUS: Record<string, string[]> = {
  pending: ["confirmed", "declined", "cancelled"],
  confirmed: ["cancelled"],
  declined: [],
  cancelled: [],
};

function AppointmentDetailBody({ tenantId, canManage }: { tenantId: string; canManage: boolean }) {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [detail, setDetail] = useState<AppointmentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);

  function load() {
    setError(null);
    getAppointmentDetail(tenantId, params.id)
      .then(setDetail)
      .catch(() => setError("Could not load this appointment request."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, params.id]);

  async function handleAction(newStatus: string) {
    if (!detail) return;
    setUpdating(true);
    setActionError(null);
    try {
      const updated = await updateAppointmentStatus(tenantId, detail.id, newStatus, detail.version);
      setDetail(updated);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setActionError("This appointment was changed by someone else. Reloading the latest version…");
        load();
      } else if (e instanceof ApiError) {
        setActionError(e.message);
      } else {
        setActionError("Could not update this appointment.");
      }
    } finally {
      setUpdating(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!detail) return <LoadingState />;

  const nextOptions = NEXT_STATUS[detail.status] ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Link href="/dashboard/appointments" className="text-sm text-neutral-500">
        ← All appointments
      </Link>

      <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <StatusBadge status={detail.status} />
          <p className="text-sm text-neutral-500">This is a request only — no live calendar exists yet.</p>
        </div>
        <dl className="text-sm grid sm:grid-cols-2 gap-2 mt-2">
          <div>
            <dt className="text-neutral-500">Requested date</dt>
            <dd>{detail.requested_date}</dd>
          </div>
          <div>
            <dt className="text-neutral-500">Time / window</dt>
            <dd>{detail.requested_time ?? detail.requested_time_window ?? "Not specified"}</dd>
          </div>
          <div>
            <dt className="text-neutral-500">Timezone</dt>
            <dd>{detail.timezone}</dd>
          </div>
          {detail.notes && (
            <div className="sm:col-span-2">
              <dt className="text-neutral-500">Visitor notes (original request)</dt>
              <dd className="whitespace-pre-wrap">{detail.notes}</dd>
            </div>
          )}
        </dl>

        {canManage && nextOptions.length > 0 ? (
          <div className="flex flex-wrap gap-2 mt-3">
            {nextOptions.map((status) => (
              <button
                key={status}
                type="button"
                disabled={updating}
                onClick={() => handleAction(status)}
                className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm capitalize disabled:opacity-50"
              >
                {status}
              </button>
            ))}
          </div>
        ) : !canManage ? (
          <p className="text-xs text-neutral-500 mt-2">Only an owner or admin can confirm, decline, or cancel an appointment.</p>
        ) : null}
        <p className="text-xs text-neutral-500 mt-2">
          Changing this status does not notify the visitor — Phase 6 has no automatic delivery mechanism.
        </p>
      </section>
      {actionError && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{actionError}</p>}

      <Link href={`/dashboard/conversations/${detail.conversation_id}`} className="rounded-lg border border-black/10 dark:border-white/10 p-4 underline text-sm w-fit">
        View linked transcript
      </Link>

      {user && <NotesPanel tenantId={tenantId} entityType="appointment_request" entityId={detail.id} currentUserId={user.id} />}
    </div>
  );
}

export default function AppointmentDetailPage() {
  const { tenantId, canManage } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Appointment request</h1>
      <AppointmentDetailBody tenantId={tenantId} canManage={canManage} />
    </>
  );
}
