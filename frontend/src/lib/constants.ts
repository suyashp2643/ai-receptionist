// Mirrors backend/app/core/allowlists.py — kept in sync manually since these
// are small, stable lists. The backend is still the source of truth/enforcement;
// this only drives UI presentation (dropdown options, human-readable labels).

export const SUGGESTED_TONES = ["friendly", "professional", "warm", "formal", "casual", "empathetic"] as const;

export const ACTION_LABELS: Record<string, string> = {
  answer_questions: "Answer questions",
  capture_contact: "Capture contact details",
  qualify_lead: "Qualify lead",
  request_callback: "Request callback",
  request_appointment: "Request appointment",
  request_viewing: "Request viewing",
  request_reservation: "Request reservation",
  request_demo: "Request demo",
  request_test_drive: "Request test drive",
  request_service_visit: "Request service visit",
  request_human_handoff: "Request human handoff",
};

export const QUALIFICATION_FIELD_TYPES = [
  "short_text",
  "long_text",
  "email",
  "phone",
  "number",
  "currency",
  "date",
  "time",
  "datetime",
  "boolean",
  "single_select",
  "multi_select",
] as const;

export const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
