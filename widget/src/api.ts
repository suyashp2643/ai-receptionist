import type {
  WidgetAppointmentRequestPayload,
  WidgetConfig,
  WidgetContactPayload,
  WidgetConversationDetail,
  WidgetHandoffRequestPayload,
  WidgetSessionStart,
  WidgetSSEEvent,
} from "./types";
import { WidgetApiError } from "./types";

const TOKEN_HEADER = "X-Widget-Session-Token";

export interface WidgetApiClientOptions {
  apiBaseUrl: string;
  publicId: string;
}

async function readJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      (body && typeof body === "object" && "error" in body && (body as { error?: { message?: string } }).error?.message) ||
      `Request failed with status ${response.status}`;
    throw new WidgetApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export class WidgetApiClient {
  private readonly base: string;
  private readonly publicId: string;

  constructor(options: WidgetApiClientOptions) {
    this.base = options.apiBaseUrl.replace(/\/+$/, "");
    this.publicId = options.publicId;
  }

  private url(path: string): string {
    return `${this.base}/api/v1/widget/${this.publicId}${path}`;
  }

  async getConfig(): Promise<WidgetConfig> {
    const response = await fetch(this.url("/config"));
    return readJsonOrThrow<WidgetConfig>(response);
  }

  async startSession(visitorReference?: string): Promise<WidgetSessionStart> {
    const response = await fetch(this.url("/sessions"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(visitorReference ? { visitor_reference: visitorReference } : {}),
    });
    return readJsonOrThrow<WidgetSessionStart>(response);
  }

  async startNewConversation(token: string, visitorReference?: string): Promise<WidgetSessionStart> {
    const response = await fetch(this.url("/conversations"), {
      method: "POST",
      headers: { "Content-Type": "application/json", [TOKEN_HEADER]: token },
      body: JSON.stringify(visitorReference ? { visitor_reference: visitorReference } : {}),
    });
    return readJsonOrThrow<WidgetSessionStart>(response);
  }

  async getConversation(token: string, conversationId: string): Promise<WidgetConversationDetail> {
    const response = await fetch(this.url(`/conversations/${conversationId}`), {
      headers: { [TOKEN_HEADER]: token },
    });
    return readJsonOrThrow<WidgetConversationDetail>(response);
  }

  async *sendMessage(
    token: string,
    conversationId: string,
    content: string,
    idempotencyKey: string
  ): AsyncGenerator<WidgetSSEEvent> {
    const response = await fetch(this.url(`/conversations/${conversationId}/messages`), {
      method: "POST",
      headers: { "Content-Type": "application/json", [TOKEN_HEADER]: token },
      body: JSON.stringify({ content, idempotency_key: idempotencyKey }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const message =
        (body && typeof body === "object" && "error" in body && (body as { error?: { message?: string } }).error?.message) ||
        `Request failed with status ${response.status}`;
      throw new WidgetApiError(response.status, message);
    }
    yield* readSSE(response);
  }

  async submitContact(token: string, payload: WidgetContactPayload): Promise<{ contact_id: string; marketing_consent: boolean }> {
    const response = await fetch(this.url("/contacts"), {
      method: "POST",
      headers: { "Content-Type": "application/json", [TOKEN_HEADER]: token },
      body: JSON.stringify(payload),
    });
    return readJsonOrThrow(response);
  }

  async submitAppointmentRequest(
    token: string,
    payload: WidgetAppointmentRequestPayload
  ): Promise<{ reference: string; status: string; message: string }> {
    const response = await fetch(this.url("/appointment-requests"), {
      method: "POST",
      headers: { "Content-Type": "application/json", [TOKEN_HEADER]: token },
      body: JSON.stringify(payload),
    });
    return readJsonOrThrow(response);
  }

  async submitHandoffRequest(
    token: string,
    payload: WidgetHandoffRequestPayload
  ): Promise<{ reference: string; status: string; message: string }> {
    const response = await fetch(this.url("/handoff-requests"), {
      method: "POST",
      headers: { "Content-Type": "application/json", [TOKEN_HEADER]: token },
      body: JSON.stringify(payload),
    });
    return readJsonOrThrow(response);
  }
}

export async function* readSSE(response: Response): AsyncGenerator<WidgetSSEEvent> {
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
        yield { event: eventName, data: JSON.parse(dataLines.join("\n")) } as WidgetSSEEvent;
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}
