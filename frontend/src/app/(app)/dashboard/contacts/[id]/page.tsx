"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { ErrorState, LoadingState } from "@/components/dashboard/ListStates";
import { NotesPanel } from "@/components/dashboard/NotesPanel";
import { getContactDetail, type ContactDetail } from "@/lib/dashboard-api";
import { useAuth } from "@/lib/auth-context";

function ContactDetailBody({ tenantId }: { tenantId: string }) {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [detail, setDetail] = useState<ContactDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    getContactDetail(tenantId, params.id)
      .then(setDetail)
      .catch(() => setError("Could not load this contact."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, params.id]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!detail) return <LoadingState />;

  return (
    <div className="flex flex-col gap-6">
      <Link href="/dashboard/contacts" className="text-sm text-neutral-500">
        ← All contacts
      </Link>

      <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-2">
        <h2 className="font-medium">{detail.name ?? "(no name)"}</h2>
        <p className="text-sm">{detail.normalized_email ?? "No email"}</p>
        <p className="text-sm">{detail.normalized_phone ?? "No phone"}</p>
        <p className="text-sm text-neutral-500">Preferred contact: {detail.preferred_contact_method ?? "not specified"}</p>
        <p className="text-sm text-neutral-500">
          Marketing consent: {detail.marketing_consent ? "Given" : "Not given"}
          {detail.consent_captured_at && ` (${new Date(detail.consent_captured_at).toLocaleString()})`}
        </p>
        <p className="text-sm text-neutral-500">First seen {new Date(detail.created_at).toLocaleString()}</p>
      </section>

      <div className="grid sm:grid-cols-2 gap-4">
        <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
          <h2 className="font-medium mb-2">Linked conversations</h2>
          {detail.conversation_ids.length === 0 ? (
            <p className="text-sm text-neutral-500">None</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {detail.conversation_ids.map((id) => (
                <li key={id}>
                  <Link href={`/dashboard/conversations/${id}`} className="text-sm underline">
                    {id.slice(0, 8)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
          <h2 className="font-medium mb-2">Linked enquiries</h2>
          {detail.enquiry_ids.length === 0 ? (
            <p className="text-sm text-neutral-500">None</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {detail.enquiry_ids.map((id) => (
                <li key={id}>
                  <Link href={`/dashboard/enquiries/${id}`} className="text-sm underline">
                    {id.slice(0, 8)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
          <h2 className="font-medium mb-2">Linked appointments</h2>
          {detail.appointment_request_ids.length === 0 ? (
            <p className="text-sm text-neutral-500">None</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {detail.appointment_request_ids.map((id) => (
                <li key={id}>
                  <Link href={`/dashboard/appointments/${id}`} className="text-sm underline">
                    {id.slice(0, 8)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-lg border border-black/10 dark:border-white/10 p-4">
          <h2 className="font-medium mb-2">Linked handoffs</h2>
          {detail.handoff_ids.length === 0 ? (
            <p className="text-sm text-neutral-500">None</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {detail.handoff_ids.map((id) => (
                <li key={id}>
                  <Link href={`/dashboard/handoffs/${id}`} className="text-sm underline">
                    {id.slice(0, 8)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {user && <NotesPanel tenantId={tenantId} entityType="contact" entityId={detail.id} currentUserId={user.id} />}
    </div>
  );
}

export default function ContactDetailPage() {
  const { tenantId } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Contact</h1>
      <ContactDetailBody tenantId={tenantId} />
    </>
  );
}
