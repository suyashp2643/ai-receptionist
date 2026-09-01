import { apiRequest, ApiError } from "@/lib/api";

// ---------- Industry templates ----------

export interface IndustryTemplateSummary {
  id: string;
  key: string;
  version: number;
  name: string;
  description: string;
  icon: string;
}

export function listIndustryTemplates() {
  return apiRequest<IndustryTemplateSummary[]>("/api/v1/industry-templates");
}

// ---------- Onboarding / business profile ----------

export interface OnboardingStepStatus {
  business_profile: boolean;
  industry_selected: boolean;
  receptionist: boolean;
  locations: boolean;
  services: boolean;
  knowledge: boolean;
  qualification: boolean;
  actions: boolean;
}

export interface BusinessProfile {
  tenant_id: string;
  business_name: string | null;
  short_description: string | null;
  website_url: string | null;
  public_email: string | null;
  public_phone: string | null;
  industry_template_id: string | null;
  timezone: string;
  default_language: string;
  supported_languages: string[];
  onboarding_status: "not_started" | "in_progress" | "completed";
  onboarding_completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface OnboardingRequirement {
  code: string;
  message: string;
  step: string;
}

export interface OnboardingState {
  status: "not_started" | "in_progress" | "completed";
  completed_at: string | null;
  ready_to_complete: boolean;
  steps: OnboardingStepStatus;
  incomplete_requirements: OnboardingRequirement[];
  business_profile: BusinessProfile | null;
}

export function getOnboardingState(tenantId: string) {
  return apiRequest<OnboardingState>(`/api/v1/tenants/${tenantId}/onboarding`);
}

export function updateBusinessProfile(tenantId: string, data: Partial<BusinessProfile>) {
  return apiRequest<BusinessProfile>(`/api/v1/tenants/${tenantId}/business-profile`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function selectIndustry(tenantId: string, templateKey: string) {
  return apiRequest<BusinessProfile>(`/api/v1/tenants/${tenantId}/select-industry`, {
    method: "POST",
    body: JSON.stringify({ template_key: templateKey }),
  });
}

export function completeOnboarding(tenantId: string) {
  return apiRequest<BusinessProfile>(`/api/v1/tenants/${tenantId}/complete-onboarding`, {
    method: "POST",
  });
}

/** Pulls the structured `requirements` list out of a failed
 * complete-onboarding call (422), if present. Returns [] for any other
 * error shape so callers can safely spread this into UI state. */
export function getRequirementsFromError(err: unknown): OnboardingRequirement[] {
  if (err instanceof ApiError && Array.isArray(err.details?.requirements)) {
    return err.details.requirements as OnboardingRequirement[];
  }
  return [];
}

// ---------- Receptionists ----------

export interface Receptionist {
  id: string;
  tenant_id: string;
  industry_template_id: string | null;
  template_version: number | null;
  name: string;
  welcome_message: string;
  tone: string | null;
  default_language: string;
  supported_languages: string[];
  logo_url: string | null;
  accent_color: string | null;
  suggested_questions: string[];
  status: "draft" | "active" | "paused";
  created_at: string;
  updated_at: string;
}

export function listReceptionists(tenantId: string) {
  return apiRequest<Receptionist[]>(`/api/v1/tenants/${tenantId}/receptionists`);
}

export function createReceptionist(tenantId: string, data: Partial<Receptionist>) {
  return apiRequest<Receptionist>(`/api/v1/tenants/${tenantId}/receptionists`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateReceptionist(tenantId: string, receptionistId: string, data: Partial<Receptionist>) {
  return apiRequest<Receptionist>(`/api/v1/tenants/${tenantId}/receptionists/${receptionistId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// ---------- Workflow (qualification + actions + safety) ----------

export interface QualificationFieldOption {
  value: string;
  label: string;
}

export interface QualificationField {
  key: string;
  label: string;
  type: string;
  description?: string | null;
  required: boolean;
  options?: QualificationFieldOption[] | null;
  min_value?: number | null;
  max_value?: number | null;
  max_length?: number | null;
  display_order: number;
  is_sensitive: boolean;
}

export interface ReceptionistWorkflow {
  id: string;
  tenant_id: string;
  receptionist_id: string;
  qualification_schema: { fields: QualificationField[] };
  qualification_rules: { rules: unknown[] };
  enabled_actions: string[];
  safety_rules: string[];
  workflow_stages: string[];
  version: number;
  created_at: string;
  updated_at: string;
}

export function getWorkflow(tenantId: string, receptionistId: string) {
  return apiRequest<ReceptionistWorkflow>(
    `/api/v1/tenants/${tenantId}/receptionists/${receptionistId}/workflow`
  );
}

export function updateWorkflow(
  tenantId: string,
  receptionistId: string,
  data: {
    qualification_schema?: { fields: QualificationField[] };
    enabled_actions?: string[];
    safety_rules?: string[];
  }
) {
  return apiRequest<ReceptionistWorkflow>(
    `/api/v1/tenants/${tenantId}/receptionists/${receptionistId}/workflow`,
    { method: "PATCH", body: JSON.stringify(data) }
  );
}

export const ALLOWED_ACTIONS = [
  "answer_questions",
  "capture_contact",
  "qualify_lead",
  "request_callback",
  "request_appointment",
  "request_viewing",
  "request_reservation",
  "request_demo",
  "request_test_drive",
  "request_service_visit",
  "request_human_handoff",
] as const;

// ---------- Locations ----------

export interface WorkingInterval {
  start: string;
  end: string;
}

export interface DayWorkingHours {
  day_of_week: number;
  closed: boolean;
  intervals: WorkingInterval[];
}

export interface BusinessLocation {
  id: string;
  tenant_id: string;
  name: string;
  address_line: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  postal_code: string | null;
  timezone: string;
  public_phone: string | null;
  working_hours: { days: DayWorkingHours[] };
  is_primary: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export function listLocations(tenantId: string) {
  return apiRequest<BusinessLocation[]>(`/api/v1/tenants/${tenantId}/locations`);
}

export function createLocation(tenantId: string, data: Record<string, unknown>) {
  return apiRequest<BusinessLocation>(`/api/v1/tenants/${tenantId}/locations`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateLocation(tenantId: string, locationId: string, data: Record<string, unknown>) {
  return apiRequest<BusinessLocation>(`/api/v1/tenants/${tenantId}/locations/${locationId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteLocation(tenantId: string, locationId: string) {
  return apiRequest<void>(`/api/v1/tenants/${tenantId}/locations/${locationId}`, { method: "DELETE" });
}

// ---------- Services ----------

export interface Service {
  id: string;
  tenant_id: string;
  location_id: string | null;
  name: string;
  description: string | null;
  category: string | null;
  price_note: string | null;
  currency: string | null;
  duration_minutes: number | null;
  is_active: boolean;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export function listServices(tenantId: string) {
  return apiRequest<Service[]>(`/api/v1/tenants/${tenantId}/services`);
}

export function createService(tenantId: string, data: Record<string, unknown>) {
  return apiRequest<Service>(`/api/v1/tenants/${tenantId}/services`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateService(tenantId: string, serviceId: string, data: Record<string, unknown>) {
  return apiRequest<Service>(`/api/v1/tenants/${tenantId}/services/${serviceId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteService(tenantId: string, serviceId: string) {
  return apiRequest<void>(`/api/v1/tenants/${tenantId}/services/${serviceId}`, { method: "DELETE" });
}

// ---------- FAQs ----------

export interface FAQ {
  id: string;
  tenant_id: string;
  question: string;
  answer: string;
  category: string | null;
  source_label: string | null;
  is_active: boolean;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export function listFaqs(tenantId: string) {
  return apiRequest<FAQ[]>(`/api/v1/tenants/${tenantId}/faqs`);
}

export function createFaq(tenantId: string, data: { question: string; answer: string }) {
  return apiRequest<{ faq: FAQ; possible_duplicate_of: string | null }>(
    `/api/v1/tenants/${tenantId}/faqs`,
    { method: "POST", body: JSON.stringify(data) }
  );
}

export function updateFaq(tenantId: string, faqId: string, data: Record<string, unknown>) {
  return apiRequest<FAQ>(`/api/v1/tenants/${tenantId}/faqs/${faqId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteFaq(tenantId: string, faqId: string) {
  return apiRequest<void>(`/api/v1/tenants/${tenantId}/faqs/${faqId}`, { method: "DELETE" });
}

// ---------- Knowledge ----------

export interface KnowledgeSource {
  id: string;
  tenant_id: string;
  type: "manual" | "website" | "file_upload";
  title: string;
  status: "active" | "inactive";
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocument {
  id: string;
  tenant_id: string;
  source_id: string;
  title: string;
  raw_text: string;
  status: "active" | "inactive";
  created_at: string;
  updated_at: string;
}

export function listKnowledgeSources(tenantId: string) {
  return apiRequest<KnowledgeSource[]>(`/api/v1/tenants/${tenantId}/knowledge/sources`);
}

export function createKnowledgeSource(tenantId: string, title: string) {
  return apiRequest<KnowledgeSource>(`/api/v1/tenants/${tenantId}/knowledge/sources`, {
    method: "POST",
    body: JSON.stringify({ type: "manual", title }),
  });
}

export function listKnowledgeDocuments(tenantId: string) {
  return apiRequest<KnowledgeDocument[]>(`/api/v1/tenants/${tenantId}/knowledge/documents`);
}

export function createKnowledgeDocument(
  tenantId: string,
  data: { source_id: string; title: string; raw_text: string }
) {
  return apiRequest<KnowledgeDocument>(`/api/v1/tenants/${tenantId}/knowledge/documents`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateKnowledgeDocument(tenantId: string, documentId: string, data: Record<string, unknown>) {
  return apiRequest<KnowledgeDocument>(`/api/v1/tenants/${tenantId}/knowledge/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteKnowledgeDocument(tenantId: string, documentId: string) {
  return apiRequest<void>(`/api/v1/tenants/${tenantId}/knowledge/documents/${documentId}`, {
    method: "DELETE",
  });
}

export interface KnowledgeSearchResult {
  document_id: string;
  document_title: string;
  chunk_id: string;
  chunk_index: number;
  content: string;
  score: number;
}

export function searchKnowledge(tenantId: string, query: string) {
  return apiRequest<{ query: string; results: KnowledgeSearchResult[] }>(
    `/api/v1/tenants/${tenantId}/knowledge/search`,
    { method: "POST", body: JSON.stringify({ query }) }
  );
}
