import { apiRequest } from "@/lib/api";

export interface WidgetInstallation {
  id: string;
  tenant_id: string;
  receptionist_id: string;
  public_id: string;
  status: "draft" | "active" | "paused" | "revoked";
  allowed_domains: string[];
  theme: Record<string, unknown>;
  launcher_position: string;
  privacy_notice: string;
  ai_disclosure: string;
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
}

export interface WidgetEmbedSnippet extends WidgetInstallation {
  embed_snippet: string;
  widget_bundle_url: string;
}

export function listWidgetInstallations(tenantId: string) {
  return apiRequest<WidgetInstallation[]>(`/api/v1/tenants/${tenantId}/widget-installations`);
}

export function createWidgetInstallation(
  tenantId: string,
  data: { receptionist_id: string; allowed_domains?: string[]; launcher_position?: string; privacy_notice?: string }
) {
  return apiRequest<WidgetInstallation>(`/api/v1/tenants/${tenantId}/widget-installations`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getWidgetEmbedSnippet(tenantId: string, installationId: string) {
  return apiRequest<WidgetEmbedSnippet>(
    `/api/v1/tenants/${tenantId}/widget-installations/${installationId}/embed-snippet`
  );
}

export function updateWidgetInstallation(
  tenantId: string,
  installationId: string,
  data: Partial<{
    allowed_domains: string[];
    theme: Record<string, unknown>;
    launcher_position: string;
    privacy_notice: string;
    ai_disclosure: string;
  }>
) {
  return apiRequest<WidgetInstallation>(`/api/v1/tenants/${tenantId}/widget-installations/${installationId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function activateWidgetInstallation(tenantId: string, installationId: string) {
  return apiRequest<WidgetInstallation>(
    `/api/v1/tenants/${tenantId}/widget-installations/${installationId}/activate`,
    { method: "POST" }
  );
}

export function pauseWidgetInstallation(tenantId: string, installationId: string) {
  return apiRequest<WidgetInstallation>(`/api/v1/tenants/${tenantId}/widget-installations/${installationId}/pause`, {
    method: "POST",
  });
}

export function revokeWidgetInstallation(tenantId: string, installationId: string) {
  return apiRequest<WidgetInstallation>(`/api/v1/tenants/${tenantId}/widget-installations/${installationId}/revoke`, {
    method: "POST",
  });
}

// ---------- Records visibility (minimal Phase 5 verification views) ----------

export interface WidgetContactRecord {
  id: string;
  conversation_id: string | null;
  name: string | null;
  normalized_email: string | null;
  normalized_phone: string | null;
  preferred_contact_method: "email" | "phone" | "either" | null;
  marketing_consent: boolean;
  consent_captured_at: string | null;
  source: string;
  created_at: string;
}

export interface WidgetEnquiryRecord {
  id: string;
  contact_id: string | null;
  conversation_id: string;
  receptionist_id: string;
  source: string;
  status: "new" | "qualified" | "closed";
  qualification_data: Record<string, unknown>;
  qualification_complete: boolean;
  recommended_next_action: string | null;
  created_at: string;
}

export interface WidgetAppointmentRequestRecord {
  id: string;
  conversation_id: string;
  contact_id: string | null;
  receptionist_id: string;
  location_id: string | null;
  service_id: string | null;
  requested_date: string;
  requested_time: string | null;
  requested_time_window: string | null;
  timezone: string;
  notes: string | null;
  status: "pending" | "confirmed" | "declined" | "cancelled";
  created_at: string;
}

export interface WidgetHandoffRecord {
  id: string;
  conversation_id: string;
  contact_id: string | null;
  receptionist_id: string;
  reason: string;
  urgency: string | null;
  preferred_contact_method: "email" | "phone" | "either" | null;
  status: "open" | "claimed" | "resolved" | "cancelled";
  created_at: string;
  resolved_at: string | null;
}

export function listWidgetContacts(tenantId: string) {
  return apiRequest<WidgetContactRecord[]>(`/api/v1/tenants/${tenantId}/widget-records/contacts`);
}

export function listWidgetEnquiries(tenantId: string) {
  return apiRequest<WidgetEnquiryRecord[]>(`/api/v1/tenants/${tenantId}/widget-records/enquiries`);
}

export function listWidgetAppointmentRequests(tenantId: string) {
  return apiRequest<WidgetAppointmentRequestRecord[]>(
    `/api/v1/tenants/${tenantId}/widget-records/appointment-requests`
  );
}

export function listWidgetHandoffRequests(tenantId: string) {
  return apiRequest<WidgetHandoffRecord[]>(`/api/v1/tenants/${tenantId}/widget-records/handoff-requests`);
}
