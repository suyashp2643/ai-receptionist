import { ApiError, apiRequest, getAccessToken, refreshAccessToken } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/config";

// ---------- REST types ----------

export interface ConversationRead {
  id: string;
  tenant_id: string;
  receptionist_id: string;
  mode: "test" | "future_live";
  channel: "dashboard_test";
  provider: string;
  status: "active" | "completed" | "abandoned" | "failed";
  visitor_reference: string | null;
  locale: string;
  collected_data: Record<string, unknown>;
  missing_required_fields: string[];
  qualification_complete: boolean;
  safety_state: Record<string, unknown>;
  last_error_code: string | null;
  started_at: string;
  last_message_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationCitation {
  source_id: string;
  source_type: string;
  title: string;
  score: number;
}

export interface ConversationMessageRead {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  sequence_number: number;
  provider_message_id: string | null;
  tool_name: string | null;
  tool_call_id: string | null;
  tool_input: Record<string, unknown> | null;
  tool_output: Record<string, unknown> | null;
  citations: ConversationCitation[];
  safety_labels: string[];
  latency_ms: number | null;
  token_usage: Record<string, unknown> | null;
  created_at: string;
}

export interface ConversationSummaryRead {
  id: string;
  conversation_id: string;
  summary: string;
  captured_requirements: Record<string, unknown>;
  unresolved_questions: string[];
  recommended_next_action: string | null;
  generated_by_provider: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface ConversationDetailResponse {
  conversation: ConversationRead;
  messages: ConversationMessageRead[];
  message_total: number;
  message_limit: number;
  message_offset: number;
  summary: ConversationSummaryRead | null;
}

export interface CompleteConversationResponse {
  conversation: ConversationRead;
  summary: ConversationSummaryRead;
}

export function startTestConversation(
  tenantId: string,
  receptionistId: string,
  data: { visitor_reference?: string; locale?: string } = {}
) {
  return apiRequest<ConversationRead>(
    `/api/v1/tenants/${tenantId}/receptionists/${receptionistId}/test-conversations`,
    { method: "POST", body: JSON.stringify(data) }
  );
}

export function listTestConversations(
  tenantId: string,
  params: { receptionistId?: string; limit?: number; offset?: number } = {}
) {
  const query = new URLSearchParams();
  if (params.receptionistId) query.set("receptionist_id", params.receptionistId);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  const qs = query.toString();
  return apiRequest<ConversationListResponse>(`/api/v1/tenants/${tenantId}/test-conversations${qs ? `?${qs}` : ""}`);
}

export function getTestConversation(
  tenantId: string,
  conversationId: string,
  params: { messageLimit?: number; messageOffset?: number } = {}
) {
  const query = new URLSearchParams();
  if (params.messageLimit) query.set("message_limit", String(params.messageLimit));
  if (params.messageOffset) query.set("message_offset", String(params.messageOffset));
  const qs = query.toString();
  return apiRequest<ConversationDetailResponse>(
    `/api/v1/tenants/${tenantId}/test-conversations/${conversationId}${qs ? `?${qs}` : ""}`
  );
}

export function completeTestConversation(tenantId: string, conversationId: string) {
  return apiRequest<CompleteConversationResponse>(
    `/api/v1/tenants/${tenantId}/test-conversations/${conversationId}/complete`,
    { method: "POST" }
  );
}

// ---------- SSE streaming ----------
// Native EventSource can't carry an Authorization header, so this reads
// the POST response's body as a stream directly via fetch — the same
// bearer-token pattern every other call in this app already uses.

export type ConversationSSEEvent =
  | {
      event: "message.started";
      data: { conversation_id: string; user_message_id: string; sequence_number: number; replay?: boolean };
    }
  | {
      event: "retrieval.completed";
      data: { count: number; sources: { source_id: string; source_type: string; title: string; score: number }[] };
    }
  | { event: "tool.started"; data: { tool_name: string; call_id: string } }
  | { event: "tool.completed"; data: { tool_name: string; call_id: string; status: "ok" | "error" } }
  | { event: "response.delta"; data: { delta: string } }
  | {
      event: "response.completed";
      data: {
        message_id: string;
        sequence_number: number;
        content: string;
        citations: ConversationCitation[];
        safety_labels: string[];
        replay?: boolean;
      };
    }
  | { event: "response.error"; data: { code: string; message: string } }
  | {
      event: "conversation.updated";
      data: {
        collected_data: Record<string, unknown>;
        missing_required_fields: string[];
        qualification_complete: boolean;
        status: string;
      };
    };

async function* readSSE(response: Response): AsyncGenerator<ConversationSSEEvent> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let eventName: string | null = null;
      const dataLines: string[] = [];
      for (const line of rawEvent.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (eventName && dataLines.length > 0) {
        yield { event: eventName, data: JSON.parse(dataLines.join("\n")) } as ConversationSSEEvent;
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export async function* streamTestMessage(
  tenantId: string,
  conversationId: string,
  body: { content: string; idempotency_key?: string },
  attempt = 0
): AsyncGenerator<ConversationSSEEvent> {
  const token = getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(
    `${getApiBaseUrl()}/api/v1/tenants/${tenantId}/test-conversations/${conversationId}/messages`,
    { method: "POST", headers, credentials: "include", body: JSON.stringify(body) }
  );

  if (response.status === 401 && attempt === 0) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      yield* streamTestMessage(tenantId, conversationId, body, 1);
      return;
    }
  }

  if (!response.ok) {
    const parsed = await response.json().catch(() => null);
    const message = parsed?.error?.message ?? `Request failed with status ${response.status}`;
    throw new ApiError(response.status, message, parsed?.error ?? null);
  }

  yield* readSSE(response);
}
