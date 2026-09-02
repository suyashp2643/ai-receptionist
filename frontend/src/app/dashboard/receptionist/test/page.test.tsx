import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReceptionistTestConsolePage from "./page";

const push = vi.fn();
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: "u1", normalized_email: "owner@example.com", display_name: "Owner", is_active: true, last_login_at: null, created_at: "2026-01-01T00:00:00Z" },
    memberships: [{ tenant_id: "tenant-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner", status: "active" }],
    isLoading: false,
  }),
}));

vi.mock("@/lib/phase3-api", () => ({
  listReceptionists: vi.fn(async () => [
    {
      id: "receptionist-1",
      tenant_id: "tenant-1",
      industry_template_id: null,
      template_version: null,
      name: "Ada",
      welcome_message: "Hi!",
      tone: "friendly",
      default_language: "en",
      supported_languages: [],
      logo_url: null,
      accent_color: null,
      suggested_questions: ["What are your hours?"],
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ]),
}));

const baseConversation = {
  id: "conv-1",
  tenant_id: "tenant-1",
  receptionist_id: "receptionist-1",
  mode: "test" as const,
  channel: "dashboard_test" as const,
  provider: "mock",
  status: "active" as const,
  visitor_reference: null,
  locale: "en",
  collected_data: {},
  missing_required_fields: [],
  qualification_complete: false,
  safety_state: {},
  last_error_code: null,
  started_at: "2026-01-01T00:00:00Z",
  last_message_at: null,
  completed_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const mockApi = vi.hoisted(() => ({
  startTestConversation: vi.fn(),
  listTestConversations: vi.fn(),
  getTestConversation: vi.fn(),
  completeTestConversation: vi.fn(),
  streamTestMessage: vi.fn(),
}));

vi.mock("@/lib/conversations-api", () => mockApi);

function setupDefaultMocks() {
  mockApi.startTestConversation.mockResolvedValue({ ...baseConversation });
  mockApi.listTestConversations.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 });
  mockApi.getTestConversation.mockResolvedValue({
    conversation: baseConversation,
    messages: [],
    message_total: 0,
    message_limit: 200,
    message_offset: 0,
    summary: null,
  });
  mockApi.completeTestConversation.mockResolvedValue({
    conversation: { ...baseConversation, status: "completed" },
    summary: {
      id: "summary-1",
      conversation_id: "conv-1",
      summary: "Test conversation summary.",
      captured_requirements: {},
      unresolved_questions: [],
      recommended_next_action: null,
      generated_by_provider: "mock",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  });
}

async function* mockStream(events: { event: string; data: Record<string, unknown> }[]) {
  for (const evt of events) {
    yield evt as never;
  }
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ReceptionistTestConsolePage", () => {
  it("shows the mock AI demonstration badge", async () => {
    setupDefaultMocks();
    render(<ReceptionistTestConsolePage />);
    expect(await screen.findByText("Mock AI demonstration")).toBeInTheDocument();
  });

  it("lists receptionists and starts a new conversation", async () => {
    setupDefaultMocks();
    const user = userEvent.setup();
    render(<ReceptionistTestConsolePage />);

    await waitFor(() => expect(screen.getByText(/Ada \(active\)/)).toBeInTheDocument());
    await user.click(screen.getByText("Start new conversation"));

    await waitFor(() => expect(mockApi.startTestConversation).toHaveBeenCalledWith("tenant-1", "receptionist-1"));
    expect(await screen.findByText(/say hello below/i)).toBeInTheDocument();
  });

  it("streams a response and updates the transcript, qualification panel, and citations", async () => {
    setupDefaultMocks();
    mockApi.streamTestMessage.mockImplementation(() =>
      mockStream([
        { event: "message.started", data: { conversation_id: "conv-1", user_message_id: "user-msg-1", sequence_number: 0 } },
        {
          event: "retrieval.completed",
          data: { count: 1, sources: [{ source_id: "faq:1", source_type: "faq", title: "Hours FAQ", score: 0.9 }] },
        },
        { event: "response.delta", data: { delta: "We're open " } },
        { event: "response.delta", data: { delta: "9-5 weekdays." } },
        {
          event: "response.completed",
          data: {
            message_id: "assistant-msg-1",
            sequence_number: 1,
            content: "We're open 9-5 weekdays.",
            citations: [{ source_id: "faq:1", source_type: "faq", title: "Hours FAQ", score: 0.9 }],
            safety_labels: [],
          },
        },
        {
          event: "conversation.updated",
          data: { collected_data: { email: "ada@example.com" }, missing_required_fields: [], qualification_complete: true, status: "active" },
        },
      ])
    );

    const user = userEvent.setup();
    render(<ReceptionistTestConsolePage />);
    await waitFor(() => expect(screen.getByText(/Ada \(active\)/)).toBeInTheDocument());
    await user.click(screen.getByText("Start new conversation"));
    await screen.findByText(/say hello below/i);

    const textarea = screen.getByPlaceholderText(/type a message/i);
    await user.type(textarea, "What are your hours?");
    await user.click(screen.getByText("Send"));

    const transcript = screen.getByRole("region", { name: /conversation transcript/i });
    expect(await within(transcript).findByText("What are your hours?")).toBeInTheDocument();
    expect(await within(transcript).findByText("We're open 9-5 weekdays.")).toBeInTheDocument();
    expect(await screen.findByText("Hours FAQ")).toBeInTheDocument();
    expect(await screen.findByText(/— complete/i)).toBeInTheDocument();
    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
  });

  it("displays tool activity events", async () => {
    setupDefaultMocks();
    mockApi.streamTestMessage.mockImplementation(() =>
      mockStream([
        { event: "message.started", data: { conversation_id: "conv-1", user_message_id: "u1", sequence_number: 0 } },
        { event: "retrieval.completed", data: { count: 0, sources: [] } },
        { event: "tool.started", data: { tool_name: "get_business_hours", call_id: "call-1" } },
        { event: "tool.completed", data: { tool_name: "get_business_hours", call_id: "call-1", status: "ok" } },
        {
          event: "response.completed",
          data: { message_id: "a1", sequence_number: 1, content: "We're open now.", citations: [], safety_labels: [] },
        },
        {
          event: "conversation.updated",
          data: { collected_data: {}, missing_required_fields: [], qualification_complete: false, status: "active" },
        },
      ])
    );

    const user = userEvent.setup();
    render(<ReceptionistTestConsolePage />);
    await waitFor(() => expect(screen.getByText(/Ada \(active\)/)).toBeInTheDocument());
    await user.click(screen.getByText("Start new conversation"));
    await screen.findByText(/say hello below/i);

    await user.type(screen.getByPlaceholderText(/type a message/i), "What are your hours?");
    await user.click(screen.getByText("Send"));

    expect(await screen.findByText("get_business_hours")).toBeInTheDocument();
    expect(await screen.findByText("ok")).toBeInTheDocument();
  });

  it("shows a safety notice when a response is safety-labeled", async () => {
    setupDefaultMocks();
    mockApi.streamTestMessage.mockImplementation(() =>
      mockStream([
        { event: "message.started", data: { conversation_id: "conv-1", user_message_id: "u1", sequence_number: 0 } },
        { event: "retrieval.completed", data: { count: 0, sources: [] } },
        {
          event: "response.completed",
          data: {
            message_id: "a1",
            sequence_number: 1,
            content: "This may be a medical emergency.",
            citations: [],
            safety_labels: ["clinic_urgent"],
          },
        },
        {
          event: "conversation.updated",
          data: { collected_data: {}, missing_required_fields: [], qualification_complete: false, status: "active" },
        },
      ])
    );

    const user = userEvent.setup();
    render(<ReceptionistTestConsolePage />);
    await waitFor(() => expect(screen.getByText(/Ada \(active\)/)).toBeInTheDocument());
    await user.click(screen.getByText("Start new conversation"));
    await screen.findByText(/say hello below/i);

    await user.type(screen.getByPlaceholderText(/type a message/i), "chest pain");
    await user.click(screen.getByText("Send"));

    const safetyBanner = await screen.findByRole("alert");
    expect(within(safetyBanner).getByText(/safety notice/i)).toBeInTheDocument();
    expect(within(safetyBanner).getByText(/clinic_urgent/)).toBeInTheDocument();
  });

  it("shows an error banner with retry on a response.error event", async () => {
    setupDefaultMocks();
    mockApi.streamTestMessage.mockImplementation(() =>
      mockStream([
        { event: "message.started", data: { conversation_id: "conv-1", user_message_id: "u1", sequence_number: 0 } },
        { event: "retrieval.completed", data: { count: 0, sources: [] } },
        { event: "response.error", data: { code: "provider_disabled", message: "The assistant is temporarily unavailable." } },
      ])
    );

    const user = userEvent.setup();
    render(<ReceptionistTestConsolePage />);
    await waitFor(() => expect(screen.getByText(/Ada \(active\)/)).toBeInTheDocument());
    await user.click(screen.getByText("Start new conversation"));
    await screen.findByText(/say hello below/i);

    await user.type(screen.getByPlaceholderText(/type a message/i), "hello");
    await user.click(screen.getByText("Send"));

    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
    expect(await screen.findByText("Retry")).toBeInTheDocument();
  });

  it("completing a conversation displays the stored summary", async () => {
    setupDefaultMocks();
    const user = userEvent.setup();
    render(<ReceptionistTestConsolePage />);
    await waitFor(() => expect(screen.getByText(/Ada \(active\)/)).toBeInTheDocument());
    await user.click(screen.getByText("Start new conversation"));
    await screen.findByText(/say hello below/i);

    await user.click(screen.getByText("Complete conversation"));

    expect(await screen.findByText("Test conversation summary.")).toBeInTheDocument();
  });

  it("reloading an existing conversation restores its transcript", async () => {
    setupDefaultMocks();
    mockApi.listTestConversations.mockResolvedValue({
      items: [{ ...baseConversation, status: "completed" }],
      total: 1,
      limit: 10,
      offset: 0,
    });
    mockApi.getTestConversation.mockResolvedValue({
      conversation: { ...baseConversation, status: "completed" },
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          role: "user",
          content: "Hello there",
          sequence_number: 0,
          provider_message_id: null,
          tool_name: null,
          tool_call_id: null,
          tool_input: null,
          tool_output: null,
          citations: [],
          safety_labels: [],
          latency_ms: null,
          token_usage: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      message_total: 1,
      message_limit: 200,
      message_offset: 0,
      summary: null,
    });

    const user = userEvent.setup();
    render(<ReceptionistTestConsolePage />);
    await waitFor(() => expect(screen.getByText(/Ada \(active\)/)).toBeInTheDocument());

    const reloadSelect = await screen.findByLabelText(/reload an existing test conversation/i);
    await user.selectOptions(reloadSelect, "conv-1");

    expect(await screen.findByText("Hello there")).toBeInTheDocument();
    expect(mockApi.getTestConversation).toHaveBeenCalledWith("tenant-1", "conv-1", { messageLimit: 200 });
  });
});
