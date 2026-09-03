import { apiRequest } from "@/lib/api";

// --- Analytics ---------------------------------------------------------

export type AnalyticsPreset = "today" | "7d" | "30d" | "custom";

export interface AnalyticsOverview {
  period_start: string;
  period_end: string;
  receptionist_id: string | null;
  include_test_preview: boolean;
  total_conversations: number;
  genuine_widget_conversations: number;
  preview_conversations: number;
  test_conversations: number;
  unique_visitor_sessions: number;
  contacts_captured: number;
  contact_capture_rate: number | null;
  enquiries_created: number;
  qualified_enquiries: number;
  qualification_completion_rate: number | null;
  appointment_requests: number;
  pending_appointments: number;
  confirmed_appointments: number;
  human_handoffs: number;
  open_handoffs: number;
  resolved_handoffs: number;
  unanswered_or_fallback_responses: number;
  safety_interventions: number;
  average_first_response_time_seconds: number | null;
  average_conversation_length_messages: number | null;
  conversation_completion_rate: number | null;
  estimated_staff_time_saved_minutes: number;
  estimated_staff_time_saved_minutes_is_estimate: boolean;
}

export interface TimeseriesPoint {
  date: string;
  conversations: number;
  appointment_requests: number;
  human_handoffs: number;
}

export interface AnalyticsFilters {
  preset: AnalyticsPreset;
  customStart?: string;
  customEnd?: string;
  receptionistId?: string;
  includeTestPreview?: boolean;
}

function analyticsQuery(filters: AnalyticsFilters): string {
  const params = new URLSearchParams();
  params.set("preset", filters.preset);
  if (filters.customStart) params.set("custom_start", filters.customStart);
  if (filters.customEnd) params.set("custom_end", filters.customEnd);
  if (filters.receptionistId) params.set("receptionist_id", filters.receptionistId);
  if (filters.includeTestPreview) params.set("include_test_preview", "true");
  return params.toString();
}

export function getAnalyticsOverview(tenantId: string, filters: AnalyticsFilters): Promise<AnalyticsOverview> {
  return apiRequest(`/api/v1/tenants/${tenantId}/analytics/overview?${analyticsQuery(filters)}`);
}

export function getAnalyticsTimeseries(
  tenantId: string,
  filters: AnalyticsFilters
): Promise<{ points: TimeseriesPoint[] }> {
  return apiRequest(`/api/v1/tenants/${tenantId}/analytics/timeseries?${analyticsQuery(filters)}`);
}

// --- Conversations -------------------------------------------------------

export type ConversationSource = "test" | "preview" | "widget";

export interface ConversationListItem {
  id: string;
  receptionist_id: string;
  started_at: string;
  last_message_at: string | null;
  status: string;
  source: ConversationSource;
  visitor_reference: string | null;
  qualification_complete: boolean;
  had_safety_event: boolean;
  had_clinic_emergency: boolean;
}

export interface ConversationListResponse {
  items: ConversationListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ConversationMessage {
  id: string;
  role: string;
  content: string;
  sequence_number: number;
  citations: unknown[];
  safety_labels: string[];
  tool_name: string | null;
  tool_input: Record<string, unknown> | null;
  tool_output: Record<string, unknown> | null;
  created_at: string;
}

export interface ConversationDashboardDetail {
  id: string;
  receptionist_id: string;
  source: ConversationSource;
  status: string;
  provider: string;
  locale: string;
  started_at: string;
  last_message_at: string | null;
  completed_at: string | null;
  qualification_complete: boolean;
  collected_data: Record<string, unknown>;
  had_safety_event: boolean;
  had_clinic_emergency: boolean;
  messages: ConversationMessage[];
  message_total: number;
  message_limit: number;
  message_offset: number;
  summary: { summary: string; recommended_next_action: string | null; unresolved_questions: string[] } | null;
  contact: { id: string; name: string | null; normalized_email: string | null; normalized_phone: string | null } | null;
  enquiry: { id: string; status: string } | null;
  appointment_requests: { id: string; status: string; requested_date: string }[];
  handoffs: { id: string; status: string }[];
}

export interface ListParams {
  limit?: number;
  offset?: number;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  receptionistId?: string;
  sortDirection?: "asc" | "desc";
}

export function listConversations(
  tenantId: string,
  params: ListParams & { source?: ConversationSource[]; status?: string[]; onlySafetyEvents?: boolean } = {}
): Promise<ConversationListResponse> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.search) q.set("search", params.search);
  if (params.dateFrom) q.set("date_from", params.dateFrom);
  if (params.dateTo) q.set("date_to", params.dateTo);
  if (params.receptionistId) q.set("receptionist_id", params.receptionistId);
  if (params.sortDirection) q.set("sort_direction", params.sortDirection);
  if (params.onlySafetyEvents) q.set("only_safety_events", "true");
  for (const s of params.source ?? []) q.append("source", s);
  for (const s of params.status ?? []) q.append("status", s);
  return apiRequest(`/api/v1/tenants/${tenantId}/conversations?${q.toString()}`);
}

export function getConversationDetail(tenantId: string, conversationId: string): Promise<ConversationDashboardDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/conversations/${conversationId}`);
}

// --- Contacts ------------------------------------------------------------

export interface ContactListItem {
  id: string;
  name: string | null;
  normalized_email: string | null;
  normalized_phone: string | null;
  preferred_contact_method: string | null;
  source: string;
  marketing_consent: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContactDetail extends ContactListItem {
  consent_captured_at: string | null;
  conversation_ids: string[];
  enquiry_ids: string[];
  appointment_request_ids: string[];
  handoff_ids: string[];
}

export function listContacts(
  tenantId: string,
  params: ListParams = {}
): Promise<{ items: ContactListItem[]; total: number; limit: number; offset: number }> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.search) q.set("search", params.search);
  if (params.dateFrom) q.set("date_from", params.dateFrom);
  if (params.dateTo) q.set("date_to", params.dateTo);
  return apiRequest(`/api/v1/tenants/${tenantId}/contacts?${q.toString()}`);
}

export function getContactDetail(tenantId: string, contactId: string): Promise<ContactDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/contacts/${contactId}`);
}

// --- Enquiries -------------------------------------------------------------

export interface EnquiryListItem {
  id: string;
  contact_id: string | null;
  receptionist_id: string;
  source: string;
  status: string;
  qualification_complete: boolean;
  recommended_next_action: string | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface EnquiryDetail extends EnquiryListItem {
  conversation_id: string;
  qualification_data: Record<string, unknown>;
}

export const ENQUIRY_STATUSES = [
  "new",
  "qualified",
  "contacted",
  "appointment_requested",
  "in_progress",
  "won",
  "lost",
  "archived",
] as const;

export function listEnquiries(
  tenantId: string,
  params: ListParams & { status?: string[] } = {}
): Promise<{ items: EnquiryListItem[]; total: number; limit: number; offset: number }> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.search) q.set("search", params.search);
  if (params.dateFrom) q.set("date_from", params.dateFrom);
  if (params.dateTo) q.set("date_to", params.dateTo);
  if (params.receptionistId) q.set("receptionist_id", params.receptionistId);
  for (const s of params.status ?? []) q.append("status", s);
  return apiRequest(`/api/v1/tenants/${tenantId}/enquiries?${q.toString()}`);
}

export function getEnquiryDetail(tenantId: string, enquiryId: string): Promise<EnquiryDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/enquiries/${enquiryId}`);
}

export function updateEnquiryStatus(
  tenantId: string,
  enquiryId: string,
  status: string,
  expectedVersion: number
): Promise<EnquiryDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/enquiries/${enquiryId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, expected_version: expectedVersion }),
  });
}

// --- Appointments ----------------------------------------------------------

export interface AppointmentListItem {
  id: string;
  contact_id: string | null;
  receptionist_id: string;
  location_id: string | null;
  service_id: string | null;
  requested_date: string;
  requested_time: string | null;
  requested_time_window: string | null;
  timezone: string;
  status: string;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface AppointmentDetail extends AppointmentListItem {
  conversation_id: string;
  notes: string | null;
}

export function listAppointments(
  tenantId: string,
  params: ListParams & { status?: string[] } = {}
): Promise<{ items: AppointmentListItem[]; total: number; limit: number; offset: number }> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.search) q.set("search", params.search);
  if (params.dateFrom) q.set("date_from", params.dateFrom);
  if (params.dateTo) q.set("date_to", params.dateTo);
  if (params.receptionistId) q.set("receptionist_id", params.receptionistId);
  for (const s of params.status ?? []) q.append("status", s);
  return apiRequest(`/api/v1/tenants/${tenantId}/appointments?${q.toString()}`);
}

export function getAppointmentDetail(tenantId: string, appointmentId: string): Promise<AppointmentDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/appointments/${appointmentId}`);
}

export function updateAppointmentStatus(
  tenantId: string,
  appointmentId: string,
  status: string,
  expectedVersion: number
): Promise<AppointmentDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/appointments/${appointmentId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, expected_version: expectedVersion }),
  });
}

// --- Handoffs ----------------------------------------------------------

export interface HandoffListItem {
  id: string;
  contact_id: string | null;
  receptionist_id: string;
  reason: string;
  urgency: string | null;
  preferred_contact_method: string | null;
  status: string;
  assigned_user_id: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  version: number;
}

export interface HandoffDetail extends HandoffListItem {
  conversation_id: string;
  is_clinic_emergency: boolean;
}

export function listHandoffs(
  tenantId: string,
  params: ListParams & { status?: string[] } = {}
): Promise<{ items: HandoffListItem[]; total: number; limit: number; offset: number }> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.search) q.set("search", params.search);
  if (params.dateFrom) q.set("date_from", params.dateFrom);
  if (params.dateTo) q.set("date_to", params.dateTo);
  if (params.receptionistId) q.set("receptionist_id", params.receptionistId);
  for (const s of params.status ?? []) q.append("status", s);
  return apiRequest(`/api/v1/tenants/${tenantId}/handoffs?${q.toString()}`);
}

export function getHandoffDetail(tenantId: string, handoffId: string): Promise<HandoffDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/handoffs/${handoffId}`);
}

export function claimHandoff(tenantId: string, handoffId: string): Promise<HandoffDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/handoffs/${handoffId}/claim`, { method: "POST" });
}

export function updateHandoffStatus(
  tenantId: string,
  handoffId: string,
  status: string,
  expectedVersion: number
): Promise<HandoffDetail> {
  return apiRequest(`/api/v1/tenants/${tenantId}/handoffs/${handoffId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, expected_version: expectedVersion }),
  });
}

// --- Internal notes ---------------------------------------------------

export type NoteEntityType = "conversation" | "contact" | "enquiry" | "appointment_request" | "human_handoff";

export interface Note {
  id: string;
  author_user_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export function listNotes(tenantId: string, entityType: NoteEntityType, entityId: string): Promise<Note[]> {
  return apiRequest(`/api/v1/tenants/${tenantId}/notes?entity_type=${entityType}&entity_id=${entityId}`);
}

export function createNote(
  tenantId: string,
  entityType: NoteEntityType,
  entityId: string,
  body: string
): Promise<Note> {
  return apiRequest(`/api/v1/tenants/${tenantId}/notes`, {
    method: "POST",
    body: JSON.stringify({ entity_type: entityType, entity_id: entityId, body }),
  });
}

export function deleteNote(tenantId: string, noteId: string): Promise<void> {
  return apiRequest(`/api/v1/tenants/${tenantId}/notes/${noteId}`, { method: "DELETE" });
}

// --- Activity ----------------------------------------------------------

export interface ActivityEvent {
  id: string;
  actor_user_id: string | null;
  action_type: string;
  entity_type: string;
  entity_id: string;
  event_metadata: Record<string, unknown>;
  created_at: string;
}

export function listActivity(
  tenantId: string,
  params: { limit?: number; offset?: number; entityType?: string; entityId?: string } = {}
): Promise<{ items: ActivityEvent[]; total: number; limit: number; offset: number }> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.entityType) q.set("entity_type", params.entityType);
  if (params.entityId) q.set("entity_id", params.entityId);
  return apiRequest(`/api/v1/tenants/${tenantId}/activity?${q.toString()}`);
}

// --- Exports ------------------------------------------------------------

export type ExportEntity = "conversations" | "contacts" | "enquiries" | "appointments" | "handoffs";

export interface ExportFilters {
  /** Repeatable `status` query param — enquiries/appointments/handoffs only. */
  statuses?: string[];
  /** Repeatable `source` query param — conversations only. */
  sources?: string[];
}

/** Downloads one CSV export. Applies the same date range and (where the
 * backend contract supports it — see app/services/export_service.py)
 * status/source filters the calling page currently has active, so the
 * export always matches what the page is showing. Throws `ApiError` (with
 * the server's own safe message) on a non-2xx response. */
export async function exportCsv(
  tenantId: string,
  entity: ExportEntity,
  dateFrom: string,
  dateTo: string,
  filters: ExportFilters = {}
): Promise<Blob> {
  const { getAccessToken, ApiError } = await import("@/lib/api");
  const { getApiBaseUrl } = await import("@/lib/config");
  const token = getAccessToken();
  const params = new URLSearchParams();
  params.set("date_from", dateFrom);
  params.set("date_to", dateTo);
  for (const s of filters.statuses ?? []) params.append("status", s);
  for (const s of filters.sources ?? []) params.append("source", s);

  const response = await fetch(`${getApiBaseUrl()}/api/v1/tenants/${tenantId}/exports/${entity}?${params.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    credentials: "include",
  });
  if (!response.ok) {
    let message = `Export failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.error?.message === "string") message = body.error.message;
    } catch {
      // Keep the generic message — the response body wasn't JSON.
    }
    throw new ApiError(response.status, message);
  }
  return response.blob();
}
