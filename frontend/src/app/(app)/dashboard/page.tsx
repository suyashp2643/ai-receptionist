"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { AnalyticsFilterBar } from "@/components/dashboard/FilterBar";
import { KpiCard, formatNumber, formatPercent, formatSeconds } from "@/components/dashboard/KpiCard";
import { SimpleBarChart } from "@/components/dashboard/SimpleBarChart";
import { ErrorState, LoadingState } from "@/components/dashboard/ListStates";
import {
  getAnalyticsOverview,
  getAnalyticsTimeseries,
  type AnalyticsOverview,
  type AnalyticsPreset,
  type TimeseriesPoint,
} from "@/lib/dashboard-api";
import { getOnboardingState, listReceptionists, type OnboardingState, type Receptionist } from "@/lib/phase3-api";
import { summarizeRequirements } from "@/lib/onboarding-progress";

function OverviewDashboard({ tenantId }: { tenantId: string }) {
  const [preset, setPreset] = useState<AnalyticsPreset>("30d");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [receptionistId, setReceptionistId] = useState("");
  const [includeTestPreview, setIncludeTestPreview] = useState(false);
  const [receptionists, setReceptionists] = useState<Receptionist[]>([]);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [points, setPoints] = useState<TimeseriesPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReceptionists(tenantId)
      .then(setReceptionists)
      .catch(() => undefined);
  }, [tenantId]);

  function load() {
    if (preset === "custom" && (!customStart || !customEnd)) return;
    setError(null);
    const filters = {
      preset,
      customStart: preset === "custom" ? customStart : undefined,
      customEnd: preset === "custom" ? customEnd : undefined,
      receptionistId: receptionistId || undefined,
      includeTestPreview,
    };
    Promise.all([getAnalyticsOverview(tenantId, filters), getAnalyticsTimeseries(tenantId, filters)])
      .then(([o, t]) => {
        setOverview(o);
        setPoints(t.points);
      })
      .catch(() => setError("Could not load analytics."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, preset, customStart, customEnd, receptionistId, includeTestPreview]);

  return (
    <div className="flex flex-col gap-6">
      <AnalyticsFilterBar
        preset={preset}
        onPresetChange={setPreset}
        customStart={customStart}
        customEnd={customEnd}
        onCustomStartChange={setCustomStart}
        onCustomEndChange={setCustomEnd}
        receptionistId={receptionistId}
        onReceptionistChange={setReceptionistId}
        receptionists={receptionists}
        includeTestPreview={includeTestPreview}
        onIncludeTestPreviewChange={setIncludeTestPreview}
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {!overview ? (
        <LoadingState label="Loading analytics…" />
      ) : (
        <>
          <p className="text-xs text-neutral-500">
            {overview.period_start} to {overview.period_end}
            {!overview.include_test_preview && " · excluding test & preview traffic"}
          </p>

          <section aria-label="Conversation metrics" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            <KpiCard label="Total conversations" value={formatNumber(overview.total_conversations)} />
            <KpiCard label="Genuine widget conversations" value={formatNumber(overview.genuine_widget_conversations)} />
            <KpiCard label="Preview conversations" value={formatNumber(overview.preview_conversations)} />
            <KpiCard label="Test conversations" value={formatNumber(overview.test_conversations)} />
            <KpiCard label="Unique visitor sessions" value={formatNumber(overview.unique_visitor_sessions)} />
            <KpiCard
              label="Conversation completion rate"
              value={formatPercent(overview.conversation_completion_rate)}
              hint="Completed / total conversations"
            />
            <KpiCard
              label="Avg. first response time"
              value={formatSeconds(overview.average_first_response_time_seconds)}
            />
            <KpiCard
              label="Avg. conversation length"
              value={overview.average_conversation_length_messages === null ? "—" : overview.average_conversation_length_messages.toFixed(1)}
              hint="Messages per conversation"
            />
          </section>

          <section aria-label="Contact and enquiry metrics" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            <KpiCard label="Contacts captured" value={formatNumber(overview.contacts_captured)} />
            <KpiCard
              label="Contact capture rate"
              value={formatPercent(overview.contact_capture_rate)}
              hint="Contacts / genuine widget conversations"
            />
            <KpiCard label="Enquiries created" value={formatNumber(overview.enquiries_created)} />
            <KpiCard label="Qualified enquiries" value={formatNumber(overview.qualified_enquiries)} />
            <KpiCard
              label="Qualification completion rate"
              value={formatPercent(overview.qualification_completion_rate)}
              hint="Qualified / total enquiries"
            />
          </section>

          <section aria-label="Appointment and handoff metrics" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            <KpiCard label="Appointment requests" value={formatNumber(overview.appointment_requests)} />
            <KpiCard label="Pending appointments" value={formatNumber(overview.pending_appointments)} />
            <KpiCard label="Confirmed appointments" value={formatNumber(overview.confirmed_appointments)} />
            <KpiCard label="Human handoffs" value={formatNumber(overview.human_handoffs)} />
            <KpiCard label="Open handoffs" value={formatNumber(overview.open_handoffs)} />
            <KpiCard label="Resolved handoffs" value={formatNumber(overview.resolved_handoffs)} />
          </section>

          <section aria-label="Safety and unresolved needs" className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <KpiCard label="Unanswered / fallback responses" value={formatNumber(overview.unanswered_or_fallback_responses)} />
            <KpiCard label="Safety interventions" value={formatNumber(overview.safety_interventions)} />
            <KpiCard
              label="Estimated staff time saved"
              value={`${Math.round(overview.estimated_staff_time_saved_minutes)} min`}
              hint="Estimate only — assumes a fixed number of minutes per handled conversation, configurable by the platform"
            />
          </section>

          {points && points.length > 0 && (
            <section aria-label="Activity over time" className="rounded-lg border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 p-4">
              <h2 className="font-medium mb-2">Activity over time</h2>
              <SimpleBarChart
                dates={points.map((p) => p.date)}
                series={[
                  { label: "Conversations", color: "#3b82f6", values: points.map((p) => p.conversations) },
                  { label: "Appointment requests", color: "#22c55e", values: points.map((p) => p.appointment_requests) },
                  { label: "Handoffs", color: "#f59e0b", values: points.map((p) => p.human_handoffs) },
                ]}
              />
            </section>
          )}
        </>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { tenantId } = useDashboardContext();
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Overview</h1>
      <OverviewBody tenantId={tenantId} />
    </>
  );
}

function OverviewBody({ tenantId }: { tenantId: string }) {
  const [onboarding, setOnboarding] = useState<OnboardingState | null>(null);

  useEffect(() => {
    getOnboardingState(tenantId)
      .then(setOnboarding)
      .catch(() => setOnboarding(null));
  }, [tenantId]);

  if (!onboarding) {
    return <LoadingState label="Loading your workspace…" />;
  }

  if (onboarding.status !== "completed") {
    return (
      <section className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-4">
        <p className="font-medium mb-1">Finish setting up your receptionist</p>
        <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-3">Your workspace isn&apos;t fully configured yet.</p>
        <Link href="/onboarding/business" className="rounded bg-foreground text-background px-4 py-2 text-sm font-medium">
          Resume setup
        </Link>
      </section>
    );
  }

  const summary = summarizeRequirements(onboarding.status, onboarding.incomplete_requirements);

  return (
    <div className="flex flex-col gap-6">
      {summary.isWarning && (
        <section className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-4">
          <p className="font-medium mb-1">Configuration needs attention</p>
          <ul className="text-sm list-disc list-inside">
            {summary.requirements.map((r) => (
              <li key={r.code}>{r.message}</li>
            ))}
          </ul>
        </section>
      )}
      <OverviewDashboard tenantId={tenantId} />
    </div>
  );
}
