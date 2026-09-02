export interface WidgetServiceOption {
  id: string;
  name: string;
  description: string | null;
}

export interface WidgetLocationOption {
  id: string;
  name: string;
  timezone: string;
}

export interface WidgetConfig {
  status: "draft" | "active" | "paused" | "revoked";
  business_name: string;
  receptionist_name: string;
  welcome_message: string;
  suggested_questions: string[];
  logo_url: string | null;
  accent_color: string | null;
  supported_languages: string[];
  voice_enabled: boolean;
  theme: Record<string, unknown>;
  launcher_position: string;
  ai_disclosure: string;
  privacy_notice: string;
  mock_mode: boolean;
  business_public_email: string | null;
  business_public_phone: string | null;
  services: WidgetServiceOption[];
  locations: WidgetLocationOption[];
}

export interface WidgetConversation {
  id: string;
  status: "active" | "completed" | "abandoned" | "failed";
  locale: string;
  qualification_complete: boolean;
  started_at: string;
  last_message_at: string | null;
}

export interface WidgetMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sequence_number: number;
  citations: { source_id: string; source_type: string; title: string; score: number }[];
  created_at: string;
}

export interface WidgetSessionStart {
  capability_token: string;
  expires_at: string;
  conversation: WidgetConversation;
}

export interface WidgetConversationDetail {
  conversation: WidgetConversation;
  messages: WidgetMessage[];
}

export type WidgetSSEEvent =
  | { event: "message.started"; data: { conversation_id: string; user_message_id: string; sequence_number: number } }
  | { event: "retrieval.completed"; data: { count: number; sources: unknown[] } }
  | { event: "tool.started"; data: { tool_name: string; call_id: string } }
  | { event: "tool.completed"; data: { tool_name: string; call_id: string; status: string } }
  | { event: "response.delta"; data: { delta: string } }
  | {
      event: "response.completed";
      data: { message_id: string; sequence_number: number; content: string; citations: unknown[]; safety_labels: string[] };
    }
  | { event: "response.error"; data: { code: string; message: string } }
  | { event: "conversation.updated"; data: { qualification_complete: boolean; status: string } };

export interface WidgetContactPayload {
  name?: string;
  email?: string;
  phone?: string;
  preferred_contact_method?: "email" | "phone" | "either";
  marketing_consent?: boolean;
}

export interface WidgetAppointmentRequestPayload {
  requested_date: string;
  requested_time?: string;
  requested_time_window?: string;
  timezone: string;
  notes?: string;
  idempotency_key?: string;
  contact?: WidgetContactPayload;
  service_id?: string;
  location_id?: string;
}

export interface WidgetHandoffRequestPayload {
  reason: string;
  urgency?: string;
  idempotency_key?: string;
  contact?: WidgetContactPayload;
}

export class WidgetApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
