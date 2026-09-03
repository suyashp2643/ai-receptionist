"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { SourceBadge, StatusBadge } from "@/components/dashboard/StatusBadge";
import { ErrorState, LoadingState } from "@/components/dashboard/ListStates";
import { NotesPanel } from "@/components/dashboard/NotesPanel";
import { getConversationDetail, type ConversationDashboardDetail } from "@/lib/dashboard-api";
import { useAuth } from "@/lib/auth-context";

const ROLE_LABEL: Record<string, string> = {
  user: "Visitor",
  assistant: "Receptionist (AI)",
  tool: "Tool activity",
  system: "System",
};

function ConversationDetailBody({ tenantId }: { tenantId: string }) {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [detail, setDetail] = useState<ConversationDashboardDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    getConversationDetail(tenantId, params.id)
      .then(setDetail)
      .catch(() => setError("Could not load this conversation."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, params.id]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!detail) return <LoadingState />;

  return (
    <div className="flex flex-col gap-6">
      <Link href="/dashboard/conversations" className="text-sm text-neutral-500">
        ← All conversations
      </Link>

      <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-wrap gap-4 items-center">
        <SourceBadge source={detail.source} />
        <StatusBadge status={detail.status} />
        <span className="text-sm text-neutral-500">Provider: {detail.provider} (mock AI)</span>
        <span className="text-sm text-neutral-500">Started {new Date(detail.started_at).toLocaleString()}</span>
        {detail.had_clinic_emergency && (
          <span className="rounded-full px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300">
            Clinic emergency — kept separate from ordinary handoffs
          </span>
        )}
      </section>

      <div className="grid lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-3">
          <h2 className="font-medium">Transcript</h2>
          <ol className="flex flex-col gap-3">
            {detail.messages.map((m) => (
              <li key={m.id} className="rounded border border-black/10 dark:border-white/10 p-3">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-xs font-medium uppercase tracking-wide text-neutral-500">
                    {ROLE_LABEL[m.role] ?? m.role}
                  </span>
                  <span className="text-xs text-neutral-400">{new Date(m.created_at).toLocaleTimeString()}</span>
                </div>
                {m.role === "tool" ? (
                  <p className="text-sm text-neutral-500 italic">
                    Tool: {m.tool_name} (read-only activity — inputs/outputs not customer-facing)
                  </p>
                ) : (
                  <p className="text-sm whitespace-pre-wrap">{m.content}</p>
                )}
                {m.citations.length > 0 && (
                  <p className="text-xs text-neutral-500 mt-1">{m.citations.length} citation(s)</p>
                )}
                {m.safety_labels.length > 0 && (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                    Safety: {m.safety_labels.join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </section>

        <div className="flex flex-col gap-4">
          <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
            <h2 className="font-medium mb-2">Qualification</h2>
            <p className="text-sm">{detail.qualification_complete ? "Complete" : "Incomplete"}</p>
            {Object.keys(detail.collected_data).length > 0 && (
              <dl className="text-sm mt-2 flex flex-col gap-1">
                {Object.entries(detail.collected_data).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2">
                    <dt className="text-neutral-500">{key}</dt>
                    <dd className="text-right">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>

          {detail.contact && (
            <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
              <h2 className="font-medium mb-2">Contact</h2>
              <p className="text-sm">{detail.contact.name ?? "—"}</p>
              <p className="text-sm text-neutral-500">{detail.contact.normalized_email ?? detail.contact.normalized_phone ?? ""}</p>
              <Link href={`/dashboard/contacts/${detail.contact.id}`} className="text-sm underline">
                View contact
              </Link>
            </section>
          )}

          {detail.enquiry && (
            <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
              <h2 className="font-medium mb-2">Linked enquiry</h2>
              <StatusBadge status={detail.enquiry.status} />
              <div>
                <Link href={`/dashboard/enquiries/${detail.enquiry.id}`} className="text-sm underline">
                  View enquiry
                </Link>
              </div>
            </section>
          )}

          {detail.appointment_requests.length > 0 && (
            <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
              <h2 className="font-medium mb-2">Appointment requests</h2>
              <ul className="flex flex-col gap-1">
                {detail.appointment_requests.map((a) => (
                  <li key={a.id} className="text-sm flex items-center justify-between">
                    <Link href={`/dashboard/appointments/${a.id}`} className="underline">
                      {a.requested_date}
                    </Link>
                    <StatusBadge status={a.status} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {detail.handoffs.length > 0 && (
            <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
              <h2 className="font-medium mb-2">Handoff requests</h2>
              <ul className="flex flex-col gap-1">
                {detail.handoffs.map((h) => (
                  <li key={h.id} className="text-sm flex items-center justify-between">
                    <Link href={`/dashboard/handoffs/${h.id}`} className="underline">
                      {h.id.slice(0, 8)}
                    </Link>
                    <StatusBadge status={h.status} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {user && (
            <NotesPanel tenantId={tenantId} entityType="conversation" entityId={detail.id} currentUserId={user.id} />
          )}
        </div>
      </div>
    </div>
  );
}

export default function ConversationDetailPage() {
  const { tenantId } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Conversation</h1>
      <ConversationDetailBody tenantId={tenantId} />
    </>
  );
}
