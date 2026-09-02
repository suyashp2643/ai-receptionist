"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { listReceptionists, type Receptionist } from "@/lib/phase3-api";
import {
  completeTestConversation,
  getTestConversation,
  listTestConversations,
  startTestConversation,
  streamTestMessage,
  type ConversationCitation,
  type ConversationMessageRead,
  type ConversationRead,
  type ConversationSummaryRead,
} from "@/lib/conversations-api";
import { buttonClass, errorMessage, inputClass, secondaryButtonClass } from "@/components/settings/shared";

interface ToolActivityEntry {
  callId: string;
  toolName: string;
  status: "started" | "ok" | "error";
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `key-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function ReceptionistTestConsolePage() {
  const { user, memberships, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const membership = memberships[0];
  const tenantId = membership?.tenant_id ?? null;

  const [receptionists, setReceptionists] = useState<Receptionist[]>([]);
  const [selectedReceptionistId, setSelectedReceptionistId] = useState<string>("");
  const [pastConversations, setPastConversations] = useState<ConversationRead[]>([]);

  const [conversation, setConversation] = useState<ConversationRead | null>(null);
  const [messages, setMessages] = useState<ConversationMessageRead[]>([]);
  const [summary, setSummary] = useState<ConversationSummaryRead | null>(null);

  const [inputValue, setInputValue] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [toolActivity, setToolActivity] = useState<ToolActivityEntry[]>([]);
  const [latestCitations, setLatestCitations] = useState<ConversationCitation[]>([]);
  const [latestSafetyLabels, setLatestSafetyLabels] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retryPayload, setRetryPayload] = useState<{ content: string; idempotencyKey: string } | null>(null);

  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  useEffect(() => {
    if (!tenantId) return;
    listReceptionists(tenantId)
      .then((list) => {
        setReceptionists(list);
        if (list.length > 0) setSelectedReceptionistId((current) => current || list[0].id);
      })
      .catch((err) => setError(errorMessage(err)));
  }, [tenantId]);

  useEffect(() => {
    if (!tenantId || !selectedReceptionistId) return;
    listTestConversations(tenantId, { receptionistId: selectedReceptionistId, limit: 10 })
      .then((res) => setPastConversations(res.items))
      .catch(() => setPastConversations([]));
  }, [tenantId, selectedReceptionistId, conversation?.id]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingContent]);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-neutral-500">Loading…</p>
      </div>
    );
  }
  if (!user || !membership || !tenantId) return null;

  const selectedReceptionist = receptionists.find((r) => r.id === selectedReceptionistId) ?? null;

  function resetConversationState() {
    setMessages([]);
    setSummary(null);
    setStreamingContent("");
    setToolActivity([]);
    setLatestCitations([]);
    setLatestSafetyLabels([]);
    setError(null);
    setRetryPayload(null);
  }

  async function handleStartConversation() {
    if (!tenantId || !selectedReceptionistId) return;
    setError(null);
    try {
      const created = await startTestConversation(tenantId, selectedReceptionistId);
      setConversation(created);
      resetConversationState();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleReload(conversationId: string) {
    if (!tenantId) return;
    setError(null);
    try {
      const detail = await getTestConversation(tenantId, conversationId, { messageLimit: 200 });
      setConversation(detail.conversation);
      setMessages(detail.messages);
      setSummary(detail.summary);
      setStreamingContent("");
      setToolActivity([]);
      setLatestCitations(detail.messages.length ? detail.messages[detail.messages.length - 1].citations : []);
      setLatestSafetyLabels([]);
      setRetryPayload(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function runStream(content: string, idempotencyKey: string) {
    if (!tenantId || !conversation) return;
    setIsStreaming(true);
    setError(null);
    setStreamingContent("");
    setToolActivity([]);

    let accumulated = "";
    try {
      for await (const evt of streamTestMessage(tenantId, conversation.id, { content, idempotency_key: idempotencyKey })) {
        switch (evt.event) {
          case "message.started": {
            const userMessage: ConversationMessageRead = {
              id: evt.data.user_message_id,
              conversation_id: conversation.id,
              role: "user",
              content,
              sequence_number: evt.data.sequence_number,
              provider_message_id: null,
              tool_name: null,
              tool_call_id: null,
              tool_input: null,
              tool_output: null,
              citations: [],
              safety_labels: [],
              latency_ms: null,
              token_usage: null,
              created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, userMessage]);
            break;
          }
          case "retrieval.completed":
            setLatestCitations(evt.data.sources.map((s) => ({ ...s })));
            break;
          case "tool.started":
            setToolActivity((prev) => [...prev, { callId: evt.data.call_id, toolName: evt.data.tool_name, status: "started" }]);
            break;
          case "tool.completed":
            setToolActivity((prev) =>
              prev.map((t) => (t.callId === evt.data.call_id ? { ...t, status: evt.data.status } : t))
            );
            break;
          case "response.delta":
            accumulated += evt.data.delta;
            setStreamingContent(accumulated);
            break;
          case "response.completed": {
            const assistantMessage: ConversationMessageRead = {
              id: evt.data.message_id,
              conversation_id: conversation.id,
              role: "assistant",
              content: evt.data.content,
              sequence_number: evt.data.sequence_number,
              provider_message_id: null,
              tool_name: null,
              tool_call_id: null,
              tool_input: null,
              tool_output: null,
              citations: evt.data.citations,
              safety_labels: evt.data.safety_labels,
              latency_ms: null,
              token_usage: null,
              created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, assistantMessage]);
            setLatestCitations(evt.data.citations);
            setLatestSafetyLabels(evt.data.safety_labels);
            setStreamingContent("");
            setRetryPayload(null);
            break;
          }
          case "response.error":
            setError(evt.data.message);
            setRetryPayload({ content, idempotencyKey });
            break;
          case "conversation.updated":
            setConversation((prev) =>
              prev
                ? {
                    ...prev,
                    collected_data: evt.data.collected_data,
                    missing_required_fields: evt.data.missing_required_fields,
                    qualification_complete: evt.data.qualification_complete,
                    status: evt.data.status as ConversationRead["status"],
                  }
                : prev
            );
            break;
        }
      }
    } catch (err) {
      setError(errorMessage(err));
      setRetryPayload({ content, idempotencyKey });
    } finally {
      setIsStreaming(false);
      setStreamingContent("");
    }
  }

  async function handleSend() {
    const content = inputValue.trim();
    if (!content || isStreaming || !conversation) return;
    setInputValue("");
    await runStream(content, newIdempotencyKey());
  }

  async function handleRetry() {
    if (!retryPayload) return;
    await runStream(retryPayload.content, retryPayload.idempotencyKey);
  }

  async function handleComplete() {
    if (!tenantId || !conversation) return;
    setError(null);
    try {
      const result = await completeTestConversation(tenantId, conversation.id);
      setConversation(result.conversation);
      setSummary(result.summary);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function handleInputKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  const isActive = conversation?.status === "active";

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-5xl mx-auto flex flex-col gap-6">
        <div>
          <Link href="/dashboard" className="text-sm text-neutral-500">
            ← Dashboard
          </Link>
        </div>

        <header className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight">Receptionist test console</h1>
          <span
            className="rounded-full bg-amber-100 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 px-3 py-1 text-xs font-medium"
            title="Responses are generated by a deterministic, rules-based demonstration engine — not a live external AI model."
          >
            Mock AI demonstration
          </span>
        </header>

        <FieldErrorBanner message={error} onRetry={retryPayload ? handleRetry : undefined} />

        <section className="rounded-lg border border-black/10 dark:border-white/15 p-4 flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Receptionist
              <select
                className={inputClass}
                value={selectedReceptionistId}
                onChange={(e) => setSelectedReceptionistId(e.target.value)}
                disabled={isStreaming}
              >
                {receptionists.length === 0 && <option value="">No receptionists yet</option>}
                {receptionists.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} ({r.status})
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className={buttonClass}
              onClick={handleStartConversation}
              disabled={!selectedReceptionistId || isStreaming}
            >
              Start new conversation
            </button>
          </div>

          {pastConversations.length > 0 && (
            <label className="flex flex-col gap-1 text-sm max-w-md">
              Reload an existing test conversation
              <select
                className={inputClass}
                value={conversation && pastConversations.some((c) => c.id === conversation.id) ? conversation.id : ""}
                onChange={(e) => e.target.value && handleReload(e.target.value)}
                disabled={isStreaming}
              >
                <option value="">Select a past conversation…</option>
                {pastConversations.map((c) => (
                  <option key={c.id} value={c.id}>
                    {new Date(c.started_at).toLocaleString()} — {c.status}
                  </option>
                ))}
              </select>
            </label>
          )}
        </section>

        {conversation && (
          <div className="flex flex-col md:flex-row gap-6">
            <div className="flex-1 flex flex-col gap-3 min-w-0">
              <section
                aria-label="Conversation transcript"
                aria-live="polite"
                className="rounded-lg border border-black/10 dark:border-white/15 p-4 h-96 overflow-y-auto flex flex-col gap-3"
              >
                {messages.length === 0 && !streamingContent && (
                  <p className="text-sm text-neutral-500">No messages yet — say hello below.</p>
                )}
                {messages
                  .filter((m) => m.role === "user" || m.role === "assistant")
                  .map((m) => (
                    <TranscriptBubble key={m.id} message={m} />
                  ))}
                {streamingContent && (
                  <div className="self-start max-w-[85%] rounded-lg bg-black/5 dark:bg-white/10 px-3 py-2 text-sm">
                    {streamingContent}
                    <span className="animate-pulse">▍</span>
                  </div>
                )}
                {isStreaming && !streamingContent && (
                  <p className="text-xs text-neutral-500">Thinking…</p>
                )}
                <div ref={transcriptEndRef} />
              </section>

              {selectedReceptionist && selectedReceptionist.suggested_questions.length > 0 && isActive && (
                <div className="flex flex-wrap gap-2">
                  {selectedReceptionist.suggested_questions.slice(0, 5).map((q) => (
                    <button
                      key={q}
                      type="button"
                      className="rounded-full border border-black/15 dark:border-white/20 px-3 py-1 text-xs"
                      onClick={() => setInputValue(q)}
                      disabled={isStreaming}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              <div className="flex flex-col gap-2">
                <label htmlFor="test-console-input" className="sr-only">
                  Message
                </label>
                <textarea
                  id="test-console-input"
                  className={inputClass}
                  rows={2}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleInputKeyDown}
                  disabled={!isActive || isStreaming}
                  placeholder={isActive ? "Type a message and press Enter to send…" : "This conversation has ended."}
                />
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    className={buttonClass}
                    onClick={handleSend}
                    disabled={!isActive || isStreaming || !inputValue.trim()}
                  >
                    {isStreaming ? "Sending…" : "Send"}
                  </button>
                  {isActive && (
                    <button type="button" className={secondaryButtonClass} onClick={handleComplete} disabled={isStreaming}>
                      Complete conversation
                    </button>
                  )}
                </div>
              </div>

              {summary && <SummaryPanel summary={summary} />}
            </div>

            <aside className="md:w-80 shrink-0 flex flex-col gap-4">
              <QualificationPanel conversation={conversation} />
              <SafetyPanel labels={latestSafetyLabels} />
              <CitationsPanel citations={latestCitations} />
              <ToolActivityPanel entries={toolActivity} />
            </aside>
          </div>
        )}

        {!conversation && (
          <p className="text-sm text-neutral-500">
            Select a receptionist above and start a new conversation, or reload a past one, to begin testing.
          </p>
        )}
      </div>
    </div>
  );
}

function TranscriptBubble({ message }: { message: ConversationMessageRead }) {
  const isUser = message.role === "user";
  return (
    <div
      className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
        isUser ? "self-end bg-foreground text-background" : "self-start bg-black/5 dark:bg-white/10"
      }`}
    >
      {message.content}
      {message.safety_labels.length > 0 && (
        <p className="mt-1 text-xs opacity-70">Safety: {message.safety_labels.join(", ")}</p>
      )}
    </div>
  );
}

function FieldErrorBanner({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/30 p-3 flex items-center justify-between gap-3">
      <p className="text-sm text-red-700 dark:text-red-400">{message}</p>
      {onRetry && (
        <button type="button" className={secondaryButtonClass} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

function QualificationPanel({ conversation }: { conversation: ConversationRead }) {
  const capturedKeys = Object.keys(conversation.collected_data);
  return (
    <section className="rounded-lg border border-black/10 dark:border-white/15 p-4">
      <h2 className="font-medium text-sm mb-2">
        Qualification {conversation.qualification_complete && <span className="text-green-600 dark:text-green-400">— complete</span>}
      </h2>
      <p className="text-xs text-neutral-500 mb-2">Captured fields</p>
      {capturedKeys.length === 0 ? (
        <p className="text-xs text-neutral-500 mb-3">None yet.</p>
      ) : (
        <ul className="text-xs mb-3 flex flex-col gap-1">
          {capturedKeys.map((key) => (
            <li key={key} className="flex justify-between gap-2">
              <span className="text-neutral-500">{key}</span>
              <span className="font-medium truncate">{String(conversation.collected_data[key])}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-neutral-500 mb-2">Missing required fields</p>
      {conversation.missing_required_fields.length === 0 ? (
        <p className="text-xs text-neutral-500">None.</p>
      ) : (
        <ul className="text-xs list-disc list-inside">
          {conversation.missing_required_fields.map((key) => (
            <li key={key}>{key}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SafetyPanel({ labels }: { labels: string[] }) {
  if (labels.length === 0) return null;
  return (
    <section
      role="alert"
      className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-4"
    >
      <h2 className="font-medium text-sm mb-1">Safety notice</h2>
      <p className="text-xs text-neutral-600 dark:text-neutral-400">
        The last response was routed through a deterministic safety response for: {labels.join(", ")}.
      </p>
    </section>
  );
}

function CitationsPanel({ citations }: { citations: ConversationCitation[] }) {
  return (
    <section className="rounded-lg border border-black/10 dark:border-white/15 p-4">
      <h2 className="font-medium text-sm mb-2">Sources used</h2>
      {citations.length === 0 ? (
        <p className="text-xs text-neutral-500">No sources were used for the latest response.</p>
      ) : (
        <ul className="text-xs flex flex-col gap-2">
          {citations.map((c) => (
            <li key={c.source_id} className="border-b border-black/5 dark:border-white/10 pb-1 last:border-0">
              <p className="font-medium truncate">{c.title}</p>
              <p className="text-neutral-500">
                {c.source_type} · score {c.score.toFixed(2)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ToolActivityPanel({ entries }: { entries: ToolActivityEntry[] }) {
  return (
    <section className="rounded-lg border border-black/10 dark:border-white/15 p-4">
      <h2 className="font-medium text-sm mb-2">Tool activity</h2>
      {entries.length === 0 ? (
        <p className="text-xs text-neutral-500">No tools were invoked for the latest response.</p>
      ) : (
        <ul className="text-xs flex flex-col gap-1">
          {entries.map((entry) => (
            <li key={entry.callId} className="flex justify-between gap-2">
              <span>{entry.toolName}</span>
              <span
                className={
                  entry.status === "ok"
                    ? "text-green-600 dark:text-green-400"
                    : entry.status === "error"
                      ? "text-red-600 dark:text-red-400"
                      : "text-neutral-500"
                }
              >
                {entry.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SummaryPanel({ summary }: { summary: ConversationSummaryRead }) {
  return (
    <section className="rounded-lg border border-black/10 dark:border-white/15 p-4">
      <h2 className="font-medium text-sm mb-2">Stored summary</h2>
      <p className="text-sm mb-3">{summary.summary}</p>
      {summary.recommended_next_action && (
        <p className="text-xs text-neutral-500 mb-2">
          Recommended next action: <span className="font-medium">{summary.recommended_next_action}</span> (not executed)
        </p>
      )}
      {summary.unresolved_questions.length > 0 && (
        <>
          <p className="text-xs text-neutral-500 mb-1">Unresolved questions</p>
          <ul className="text-xs list-disc list-inside">
            {summary.unresolved_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
