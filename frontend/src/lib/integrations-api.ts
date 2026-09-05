import { apiRequest } from "@/lib/api";

// --- Types, mirroring backend/app/schemas/integration.py exactly -------

export const CONNECTOR_TYPES = ["mock", "webhook", "revenue_brain", "sales_employee"] as const;
export type ConnectorType = (typeof CONNECTOR_TYPES)[number];

export const EVENT_TYPES = [
  "contact.captured",
  "enquiry.created",
  "enquiry.qualified",
  "enquiry.status_changed",
  "appointment_request.created",
  "appointment_request.status_changed",
  "human_handoff.requested",
  "human_handoff.status_changed",
  "conversation.completed",
  "conversation.abandoned",
  "safety.escalation_detected",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

/** Event types that carry PII (a contact's name/email/phone) or a safety
 * classification — surfaced in the UI so an owner/admin sees a clear
 * consent/scope warning before subscribing a connection to them. Kept
 * here (not derived from the backend) so the warning text can be
 * reviewed/edited independently of the wire contract. */
export const PII_EVENT_TYPES = new Set<EventType>([
  "contact.captured",
  "enquiry.created",
  "enquiry.qualified",
  "appointment_request.created",
  "human_handoff.requested",
]);
export const SAFETY_EVENT_TYPES = new Set<EventType>(["safety.escalation_detected"]);

/** Sales Employee connections may never subscribe to a safety event — see
 * app/integrations/connectors/sales_employee.py. Mirrored here purely for
 * the create/edit form to disable the option and explain why; the
 * backend re-validates this regardless (never trust the client). */
export const SALES_EMPLOYEE_DISALLOWED_EVENT_TYPES = new Set<EventType>(["safety.escalation_detected"]);

export interface IntegrationConnection {
  id: string;
  connector_type: ConnectorType;
  name: string;
  status: "configured" | "verified" | "paused" | "failing" | "disabled";
  config: Record<string, unknown>;
  enabled_event_types: string[];
  has_signing_secret: boolean;
  inbound_api_key_prefix: string | null;
  inbound_api_key_last_four: string | null;
  failure_count: number;
  last_verified_at: string | null;
  last_delivery_at: string | null;
  last_delivery_status: string | null;
  last_inbound_event_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface InboundApiKeyCreated {
  api_key: string;
  prefix: string;
  last_four: string;
}

export interface IntegrationVerifyResult {
  success: boolean;
  error_summary: string | null;
}

export interface IntegrationOutboxEventItem {
  id: string;
  event_type: string;
  event_version: number;
  status: "pending" | "claimed" | "delivered" | "dead_letter";
  attempt_count: number;
  available_at: string;
  delivered_at: string | null;
  dead_lettered_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface ConnectionStatusBreakdown {
  active: number;
  paused: number;
  failing: number;
  disabled: number;
  total: number;
}

export interface DeliveryLatencySummary {
  p50_ms: number | null;
  p95_ms: number | null;
  sample_size: number;
}

export interface HealthWarning {
  code: string;
  message: string;
  connection_id: string | null;
}

export interface TenantIntegrationHealth {
  window_hours: number;
  connections: ConnectionStatusBreakdown;
  pending_events: number;
  retry_backlog: number;
  oldest_pending_age_seconds: number | null;
  dead_letter_count: number;
  successful_deliveries: number;
  failed_deliveries: number;
  success_rate: number | null;
  latency: DeliveryLatencySummary;
  last_success_at: string | null;
  last_failure_at: string | null;
  warnings: HealthWarning[];
}

// --- Connection CRUD + actions -----------------------------------------

export function listIntegrations(tenantId: string): Promise<{ items: IntegrationConnection[] }> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations`);
}

export function getIntegration(tenantId: string, connectionId: string): Promise<IntegrationConnection> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}`);
}

export function createIntegration(
  tenantId: string,
  payload: {
    connector_type: ConnectorType;
    name: string;
    config: Record<string, unknown>;
    enabled_event_types: string[];
    signing_secret?: string | null;
  }
): Promise<IntegrationConnection> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateIntegration(
  tenantId: string,
  connectionId: string,
  payload: { config: Record<string, unknown>; enabled_event_types: string[]; expected_version: number }
): Promise<IntegrationConnection> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function rotateSigningSecret(
  tenantId: string,
  connectionId: string,
  newSecret: string,
  expectedVersion: number
): Promise<IntegrationConnection> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/rotate-secret`, {
    method: "POST",
    body: JSON.stringify({ new_secret: newSecret, expected_version: expectedVersion }),
  });
}

export function generateInboundApiKey(
  tenantId: string,
  connectionId: string,
  expectedVersion: number
): Promise<InboundApiKeyCreated> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/inbound-key`, {
    method: "POST",
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function pauseIntegration(
  tenantId: string,
  connectionId: string,
  expectedVersion: number
): Promise<IntegrationConnection> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/pause`, {
    method: "POST",
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function resumeIntegration(
  tenantId: string,
  connectionId: string,
  expectedVersion: number
): Promise<IntegrationConnection> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/resume`, {
    method: "POST",
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function disableIntegration(
  tenantId: string,
  connectionId: string,
  expectedVersion: number
): Promise<IntegrationConnection> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/disable`, {
    method: "POST",
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function verifyIntegration(tenantId: string, connectionId: string): Promise<IntegrationVerifyResult> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/verify`, { method: "POST" });
}

export function sendTestEvent(tenantId: string, connectionId: string): Promise<IntegrationOutboxEventItem> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/test-event`, { method: "POST" });
}

export interface ProcessPendingNowResult {
  claimed: number;
  delivered: number;
  retried: number;
  dead_lettered: number;
}

/** An on-demand, synchronous delivery pass scoped to exactly this
 * connection — never touches another connection's or another tenant's
 * backlog. Not a scheduler: runs exactly once per call. Used by the
 * integration lab so a demo doesn't need the CLI worker running
 * separately. */
export function processPendingNow(tenantId: string, connectionId: string): Promise<ProcessPendingNowResult> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/process-pending`, { method: "POST" });
}

export function previewFieldMapping(
  tenantId: string,
  connectionId: string,
  sampleData: Record<string, unknown>,
  fieldMapping: Record<string, unknown>
): Promise<{ result: Record<string, unknown> }> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/preview-mapping`, {
    method: "POST",
    body: JSON.stringify({ sample_data: sampleData, field_mapping: fieldMapping }),
  });
}

export function listDeliveries(
  tenantId: string,
  connectionId: string,
  params: { limit?: number; offset?: number } = {}
): Promise<{ items: IntegrationOutboxEventItem[]; total: number; limit: number; offset: number }> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/deliveries?${q.toString()}`);
}

export function replayDelivery(
  tenantId: string,
  connectionId: string,
  eventId: string
): Promise<IntegrationOutboxEventItem> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/${connectionId}/deliveries/${eventId}/replay`, {
    method: "POST",
  });
}

export function getIntegrationHealth(
  tenantId: string,
  windowHours: number = 24
): Promise<TenantIntegrationHealth> {
  return apiRequest(`/api/v1/tenants/${tenantId}/integrations/health?window_hours=${windowHours}`);
}

// --- Display helpers ----------------------------------------------------

export const CONNECTOR_TYPE_LABELS: Record<ConnectorType, string> = {
  mock: "Mock (testing only)",
  webhook: "Generic webhook",
  revenue_brain: "Revenue Brain",
  sales_employee: "AI Sales Employee",
};

export function connectorRequiresDestinationUrl(connectorType: ConnectorType): boolean {
  return connectorType !== "mock";
}

export function connectorRequiresSigningSecret(connectorType: ConnectorType): boolean {
  return connectorType !== "mock";
}

export function allowedEventTypesFor(connectorType: ConnectorType): readonly EventType[] {
  if (connectorType === "sales_employee") {
    return EVENT_TYPES.filter((t) => !SALES_EMPLOYEE_DISALLOWED_EVENT_TYPES.has(t));
  }
  return EVENT_TYPES;
}
