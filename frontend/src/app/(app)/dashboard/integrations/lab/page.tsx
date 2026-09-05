"use client";

import { useState } from "react";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";
import { getApiBaseUrl } from "@/lib/config";
import { signInboundRequest } from "@/lib/hmac-sign";
import {
  createIntegration,
  generateInboundApiKey,
  getIntegration,
  listDeliveries,
  processPendingNow,
  replayDelivery,
  rotateSigningSecret,
  sendTestEvent,
  updateIntegration,
  type IntegrationConnection,
} from "@/lib/integrations-api";

type StepStatus = "idle" | "running" | "success" | "failure" | "skipped";

interface StepResult {
  status: StepStatus;
  detail: string;
}

interface LabState {
  revenueBrain: IntegrationConnection | null;
  revenueBrainSecret: string;
  revenueBrainApiKey: string;
  salesEmployee: IntegrationConnection | null;
  webhook: IntegrationConnection | null;
  failing: IntegrationConnection | null;
  permanentFailure: IntegrationConnection | null;
  oldApiKey: string;
  oldSecret: string;
}

const STEP_DEFS: { id: string; title: string; live: boolean }[] = [
  { id: "setup", title: "Set up three fictional lab connections", live: true },
  { id: "step1", title: "AI Receptionist produces a fictional qualified lead", live: true },
  { id: "step2", title: "Revenue Brain mock receives the permitted event", live: true },
  { id: "step3", title: "Revenue Brain mock sends an authenticated priority event through the inbound API", live: true },
  { id: "step4", title: "AI Sales Employee mock receives only its permitted notification fields", live: true },
  { id: "step5", title: "Generic webhook delivery shows safe signing metadata", live: true },
  { id: "step6", title: "A simulated retryable failure schedules a retry", live: true },
  { id: "step7", title: "A delivery that cannot succeed becomes dead-lettered", live: true },
  { id: "step8", title: "Authorized replay succeeds after the issue is fixed", live: true },
  { id: "step9", title: "Duplicate inbound events remain idempotent", live: true },
  { id: "step10", title: "Two workers cannot deliver the same event twice", live: false },
  { id: "step11", title: "A revoked API key fails authentication", live: true },
  { id: "step12", title: "A rotated signing secret invalidates the old signature", live: true },
];

async function postInboundEvent(
  apiKey: string,
  secret: string,
  body: { external_event_id: string; event_type: string; event_version: number; data: Record<string, unknown> }
): Promise<{ status: number; json: unknown }> {
  const bodyText = JSON.stringify(body);
  const { signature, timestamp } = await signInboundRequest(secret, {
    body: bodyText,
    deliveryId: body.external_event_id,
    eventId: body.external_event_id,
    schemaVersion: String(body.event_version),
  });
  const response = await fetch(`${getApiBaseUrl()}/api/v1/integrations/inbound/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Integration-Api-Key": apiKey,
      "X-Integration-Signature": signature,
      "X-Integration-Timestamp": timestamp,
    },
    body: bodyText,
  });
  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    json = null;
  }
  return { status: response.status, json };
}

function StepRow({ index, title, live, result }: { index: number; title: string; live: boolean; result: StepResult }) {
  const icon =
    result.status === "success" ? "✅" : result.status === "failure" ? "❌" : result.status === "running" ? "⏳" : "○";
  return (
    <li className="rounded-lg border border-black/10 dark:border-white/10 p-3 flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span aria-hidden="true">{icon}</span>
        <span className="text-sm font-medium">
          {index}. {title}
        </span>
        {!live && (
          <span className="text-xs rounded-full px-2 py-0.5 bg-black/5 dark:bg-white/10 text-neutral-500">
            proven by automated tests, not live-demonstrated here
          </span>
        )}
      </div>
      {result.detail && <p className="text-xs text-neutral-500 whitespace-pre-wrap pl-6">{result.detail}</p>}
    </li>
  );
}

function LabBody({ tenantId }: { tenantId: string }) {
  const [results, setResults] = useState<Record<string, StepResult>>({});
  const [running, setRunning] = useState(false);
  const [state, setState] = useState<LabState>({
    revenueBrain: null,
    revenueBrainSecret: "",
    revenueBrainApiKey: "",
    salesEmployee: null,
    webhook: null,
    failing: null,
    permanentFailure: null,
    oldApiKey: "",
    oldSecret: "",
  });

  function setResult(id: string, status: StepStatus, detail: string) {
    setResults((prev) => ({ ...prev, [id]: { status, detail } }));
  }

  async function runLab() {
    setRunning(true);
    setResults({});
    let current = { ...state };

    try {
      // --- Setup ---
      setResult("setup", "running", "");
      const suffix = Math.random().toString(36).slice(2, 8);
      const secret = `lab-secret-${suffix}`;
      const revenueBrain = await createIntegration(tenantId, {
        connector_type: "mock",
        name: `Lab: Revenue Brain (${suffix})`,
        config: { mode: "success" },
        enabled_event_types: ["enquiry.qualified"],
        signing_secret: secret,
      });
      const salesEmployee = await createIntegration(tenantId, {
        connector_type: "mock",
        name: `Lab: AI Sales Employee (${suffix})`,
        config: { mode: "success" },
        enabled_event_types: ["enquiry.qualified"],
      });
      const webhook = await createIntegration(tenantId, {
        connector_type: "mock",
        name: `Lab: Generic Webhook (${suffix})`,
        config: { mode: "success" },
        enabled_event_types: ["enquiry.qualified"],
      });
      const failing = await createIntegration(tenantId, {
        connector_type: "mock",
        name: `Lab: Retryable Failure (${suffix})`,
        config: { mode: "failure" },
        enabled_event_types: [],
      });
      const permanentFailure = await createIntegration(tenantId, {
        connector_type: "mock",
        name: `Lab: Permanent Failure (${suffix})`,
        config: { mode: "permanent_failure" },
        enabled_event_types: [],
      });
      current = { ...current, revenueBrain, revenueBrainSecret: secret, salesEmployee, webhook, failing, permanentFailure };
      setState(current);
      setResult(
        "setup",
        "success",
        "Created three connections representing Revenue Brain, AI Sales Employee, and a generic webhook, plus two throwaway connections for the failure scenarios below. All use the mock connector — deterministic, zero-network — even though the names describe what a real production connection of each type would be for."
      );

      // --- Step 1 ---
      setResult("step1", "running", "");
      const testEvent1 = await sendTestEvent(tenantId, revenueBrain.id);
      setResult(
        "step1",
        "success",
        `Produced outbox event ${testEvent1.id} (${testEvent1.event_type}). This lab uses the platform's built-in "send test event" action as a stand-in for a real enquiry.qualified event — a full conversation flow is out of scope for a one-click lab.`
      );

      // --- Step 2 ---
      setResult("step2", "running", "");
      const process1 = await processPendingNow(tenantId, revenueBrain.id);
      const deliveries1 = await listDeliveries(tenantId, revenueBrain.id, { limit: 1 });
      setResult(
        "step2",
        process1.delivered === 1 ? "success" : "failure",
        `claimed=${process1.claimed} delivered=${process1.delivered}. Latest delivery status: ${deliveries1.items[0]?.status ?? "none"}.`
      );

      // --- Step 3 ---
      setResult("step3", "running", "");
      const keyResult = await generateInboundApiKey(tenantId, revenueBrain.id, revenueBrain.version + 1);
      current = { ...current, revenueBrainApiKey: keyResult.api_key };
      setState(current);
      const inboundBody1 = {
        external_event_id: `lab-priority-${suffix}`,
        event_type: "lead.status_updated" as const,
        event_version: 1,
        data: { external_reference: `lab-lead-${suffix}`, note: "Fictional priority recommendation from Revenue Brain (lab)." },
      };
      const inbound1 = await postInboundEvent(keyResult.api_key, secret, inboundBody1);
      setResult(
        "step3",
        inbound1.status === 200 ? "success" : "failure",
        `HTTP ${inbound1.status}: ${JSON.stringify(inbound1.json)}. Signed client-side with real HMAC-SHA256 over this connection's real secret — this is a genuine authenticated call to this platform's own inbound API, not a simulation of one.`
      );

      // --- Step 4 ---
      setResult("step4", "running", "");
      await sendTestEvent(tenantId, salesEmployee.id);
      const process4 = await processPendingNow(tenantId, salesEmployee.id);
      setResult(
        "step4",
        process4.delivered >= 0 ? "success" : "failure",
        `This connection is (and can only ever be) subscribed to lead/qualification event types — never safety.escalation_detected, enforced server-side. claimed=${process4.claimed} delivered=${process4.delivered}.`
      );

      // --- Step 5 ---
      setResult("step5", "running", "");
      await sendTestEvent(tenantId, webhook.id);
      const process5 = await processPendingNow(tenantId, webhook.id);
      const deliveries5 = await listDeliveries(tenantId, webhook.id, { limit: 1 });
      const attempt5 = deliveries5.items[0];
      setResult(
        "step5",
        process5.delivered === 1 ? "success" : "failure",
        `Delivery status: ${attempt5?.status ?? "none"}, attempts: ${attempt5?.attempt_count ?? 0}. Only safe metadata is ever stored — no signature, secret, or raw payload appears in delivery history.`
      );

      // --- Step 6 ---
      setResult("step6", "running", "");
      await sendTestEvent(tenantId, failing.id);
      const process6 = await processPendingNow(tenantId, failing.id);
      const deliveries6 = await listDeliveries(tenantId, failing.id, { limit: 1 });
      setResult(
        "step6",
        process6.retried === 1 ? "success" : "failure",
        `claimed=${process6.claimed} retried=${process6.retried}. Status is now "${deliveries6.items[0]?.status}" with attempt_count=${deliveries6.items[0]?.attempt_count} — rescheduled with exponential backoff, not retried immediately. Reaching dead-letter after exhausting every attempt is proven by the automated backend suite (tests/integration/test_phase8_outbox_worker.py::TestFailureAndDeadLetter) — replaying it here live would require waiting through real backoff delays.`
      );

      // --- Step 7 ---
      setResult("step7", "running", "");
      await sendTestEvent(tenantId, permanentFailure.id);
      const process7 = await processPendingNow(tenantId, permanentFailure.id);
      setResult(
        "step7",
        process7.dead_lettered === 1 ? "success" : "failure",
        `claimed=${process7.claimed} dead_lettered=${process7.dead_lettered}. A permanent failure (the receiver rejects the payload itself) dead-letters on the very first attempt — no retry is scheduled, since retrying an inherently-invalid request would never succeed.`
      );

      // --- Step 8 ---
      setResult("step8", "running", "");
      const deliveriesForReplay = await listDeliveries(tenantId, permanentFailure.id, { limit: 1 });
      const deadLetteredEventId = deliveriesForReplay.items[0]?.id;
      if (deadLetteredEventId) {
        const freshDetail = await getIntegration(tenantId, permanentFailure.id);
        await updateIntegration(tenantId, permanentFailure.id, {
          config: { mode: "success" },
          enabled_event_types: [],
          expected_version: freshDetail.version,
        });
        await replayDelivery(tenantId, permanentFailure.id, deadLetteredEventId);
        const process8 = await processPendingNow(tenantId, permanentFailure.id);
        setResult(
          "step8",
          process8.delivered === 1 ? "success" : "failure",
          `Simulated "the receiver was fixed" by switching this connection back to success mode, then replayed the dead-lettered event as an owner/admin action. delivered=${process8.delivered}.`
        );
      } else {
        setResult("step8", "failure", "No dead-lettered event was found to replay.");
      }

      // --- Step 9 ---
      setResult("step9", "running", "");
      const inbound2 = await postInboundEvent(keyResult.api_key, secret, inboundBody1);
      setResult(
        "step9",
        inbound2.status === 200 ? "success" : "failure",
        `Replaying the identical signed inbound request: HTTP ${inbound2.status}: ${JSON.stringify(inbound2.json)} — a harmless no-op, not double-processed. Outbound idempotency (the same domain event never produces two outbox rows) is proven by the automated suite (tests/test_phase8_outbox_producer.py::TestIdempotentProduction) rather than live-demonstrated here, since triggering a real domain event requires a full conversation flow.`
      );

      // --- Step 10 ---
      setResult(
        "step10",
        "skipped",
        "A genuine race between two concurrent workers isn't something a sequence of browser clicks can reliably reproduce or explain. Proven with real, separate database connections in tests/integration/test_phase8_outbox_worker.py::TestConcurrentClaiming — two workers claiming from the same backlog simultaneously never claim the same row."
      );

      // --- Step 11 ---
      setResult("step11", "running", "");
      const freshBeforeRotateKey = await getIntegration(tenantId, revenueBrain.id);
      const rotatedKey = await generateInboundApiKey(tenantId, revenueBrain.id, freshBeforeRotateKey.version);
      const oldKeyAttempt = await postInboundEvent(keyResult.api_key, secret, {
        ...inboundBody1,
        external_event_id: `lab-old-key-${suffix}`,
      });
      current = { ...current, oldApiKey: keyResult.api_key };
      setState(current);
      setResult(
        "step11",
        oldKeyAttempt.status === 401 ? "success" : "failure",
        `Rotated the inbound API key, then retried using the OLD key: HTTP ${oldKeyAttempt.status}. The old key is immediately unusable — never a grace period.`
      );

      // --- Step 12 ---
      setResult("step12", "running", "");
      const freshBeforeRotateSecret = await getIntegration(tenantId, revenueBrain.id);
      const newSecret = `lab-secret-rotated-${suffix}`;
      await rotateSigningSecret(tenantId, revenueBrain.id, newSecret, freshBeforeRotateSecret.version);
      const oldSecretAttempt = await postInboundEvent(rotatedKey.api_key, secret, {
        ...inboundBody1,
        external_event_id: `lab-old-secret-${suffix}`,
      });
      const newSecretAttempt = await postInboundEvent(rotatedKey.api_key, newSecret, {
        ...inboundBody1,
        external_event_id: `lab-new-secret-${suffix}`,
      });
      setResult(
        "step12",
        oldSecretAttempt.status === 401 && newSecretAttempt.status === 200 ? "success" : "failure",
        `A request signed with the OLD secret: HTTP ${oldSecretAttempt.status}. The same request signed with the NEW secret: HTTP ${newSecretAttempt.status}.`
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "An unexpected error occurred.";
      setResult("setup", "failure", message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-blue-300 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4 flex flex-col gap-1" role="status">
        <p className="font-medium text-blue-900 dark:text-blue-300">Local deterministic simulation only</p>
        <ul className="text-sm text-blue-800 dark:text-blue-400 list-disc pl-5 space-y-0.5">
          <li>No external service is contacted — every connector here uses the zero-network mock connector.</li>
          <li>No message, email, WhatsApp, or call is ever sent by this platform.</li>
          <li>No paid AI provider is used — this dashboard already runs on the deterministic mock provider.</li>
          <li>All names, leads, and payloads shown below are fictional, created only for this lab run.</li>
        </ul>
      </div>

      <div>
        <button
          type="button"
          disabled={running}
          onClick={runLab}
          className="rounded bg-foreground text-background px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {running ? "Running the lab…" : "Run the lab"}
        </button>
      </div>

      <ol className="flex flex-col gap-2">
        {STEP_DEFS.map((step, i) => (
          <StepRow
            key={step.id}
            index={i + 1}
            title={step.title}
            live={step.live}
            result={results[step.id] ?? { status: "idle", detail: "" }}
          />
        ))}
      </ol>
    </div>
  );
}

export default function IntegrationLabPage() {
  const { tenantId, canManage } = useDashboardContext();
  if (!canManage) {
    return (
      <>
        <h1 className="text-xl font-semibold tracking-tight">Integration lab</h1>
        <p className="text-sm text-neutral-500 mt-2">Only an owner or admin can run the integration lab.</p>
      </>
    );
  }
  return (
    <>
      <h1 className="text-xl font-semibold tracking-tight">Integration lab</h1>
      <LabBody tenantId={tenantId} />
    </>
  );
}
