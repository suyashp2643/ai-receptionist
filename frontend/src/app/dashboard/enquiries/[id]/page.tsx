"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { StatusBadge } from "@/components/dashboard/StatusBadge";
import { ErrorState, LoadingState } from "@/components/dashboard/ListStates";
import { NotesPanel } from "@/components/dashboard/NotesPanel";
import { ApiError } from "@/lib/api";
import { ENQUIRY_STATUSES, getEnquiryDetail, updateEnquiryStatus, type EnquiryDetail } from "@/lib/dashboard-api";
import { useAuth } from "@/lib/auth-context";

function EnquiryDetailBody({ tenantId }: { tenantId: string }) {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [detail, setDetail] = useState<EnquiryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);

  function load() {
    setError(null);
    getEnquiryDetail(tenantId, params.id)
      .then(setDetail)
      .catch(() => setError("Could not load this enquiry."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, params.id]);

  async function handleStatusChange(newStatus: string) {
    if (!detail || newStatus === detail.status) return;
    setUpdating(true);
    setStatusError(null);
    try {
      const updated = await updateEnquiryStatus(tenantId, detail.id, newStatus, detail.version);
      setDetail(updated);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setStatusError("This enquiry was changed by someone else. Reloading the latest version…");
        load();
      } else if (e instanceof ApiError) {
        setStatusError(e.message);
      } else {
        setStatusError("Could not update status.");
      }
    } finally {
      setUpdating(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!detail) return <LoadingState />;

  return (
    <div className="flex flex-col gap-6">
      <Link href="/dashboard/enquiries" className="text-sm text-neutral-500">
        ← All enquiries
      </Link>

      <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-wrap items-center gap-4">
        <StatusBadge status={detail.status} />
        <div className="flex flex-col gap-1">
          <label htmlFor="enquiry-status-select" className="text-xs text-neutral-500">
            Change status
          </label>
          <select
            id="enquiry-status-select"
            value={detail.status}
            disabled={updating}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
          >
            {ENQUIRY_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
        <p className="text-xs text-neutral-500">
          &lsquo;Won&rsquo; and &lsquo;lost&rsquo; are manual labels for your own tracking — this system does not calculate revenue.
        </p>
      </section>
      {statusError && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{statusError}</p>}

      <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
        <h2 className="font-medium mb-2">Captured requirements</h2>
        {Object.keys(detail.qualification_data).length === 0 ? (
          <p className="text-sm text-neutral-500">Nothing captured yet.</p>
        ) : (
          <dl className="text-sm flex flex-col gap-1">
            {Object.entries(detail.qualification_data).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-2">
                <dt className="text-neutral-500">{key}</dt>
                <dd className="text-right">{String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <div className="grid sm:grid-cols-2 gap-4">
        <Link href={`/dashboard/conversations/${detail.conversation_id}`} className="rounded-lg border border-black/10 dark:border-white/10 p-4 underline text-sm">
          View linked transcript
        </Link>
        {detail.contact_id && (
          <Link href={`/dashboard/contacts/${detail.contact_id}`} className="rounded-lg border border-black/10 dark:border-white/10 p-4 underline text-sm">
            View contact
          </Link>
        )}
      </div>

      {user && <NotesPanel tenantId={tenantId} entityType="enquiry" entityId={detail.id} currentUserId={user.id} />}
    </div>
  );
}

export default function EnquiryDetailPage() {
  const { tenantId } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Enquiry</h1>
      <EnquiryDetailBody tenantId={tenantId} />
    </>
  );
}
