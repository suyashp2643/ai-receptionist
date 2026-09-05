import { WidgetApiClient } from "./api";
import { buildStyles } from "./styles";
import { clearStoredSession, loadStoredSession, saveStoredSession } from "./storage";
import type { WidgetConfig, WidgetMessage, WidgetSSEEvent } from "./types";
import { WidgetApiError } from "./types";
import {
  isSpeechRecognitionSupported,
  isSpeechSynthesisSupported,
  VoiceRecognizer,
  VoiceSpeaker,
  type VoiceRecognitionErrorReason,
} from "./voice";

export interface WidgetOptions {
  publicId: string;
  apiBaseUrl: string;
  /** Threaded into every session-creation call's `visitor_reference` — used
   * by the dashboard's "live local preview" to mark preview traffic
   * distinctly from real visitors (see docs/architecture.md). A real embed
   * never sets this. */
  visitorReference?: string;
  /** Namespaces this instance's sessionStorage key so a preview page's
   * "Restart preview" can force a fresh conversation by generating a new
   * namespace, without touching any other instance's stored session. A
   * real embed never sets this. */
  sessionNamespace?: string;
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `key-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

type FormKind = "contact" | "appointment" | "handoff" | null;

/**
 * Owns exactly one widget instance's Shadow DOM, state, and lifecycle.
 * Never touches anything outside its own shadow root or the single host
 * element it was given — see index.ts for the duplicate-mount guard that
 * ensures at most one of these exists per page.
 */
export class Widget {
  private readonly api: WidgetApiClient;
  private readonly publicId: string;
  private readonly visitorReference?: string;
  private readonly sessionNamespace?: string;
  private readonly host: HTMLElement;
  private readonly shadow: ShadowRoot;
  private readonly recognizer = new VoiceRecognizer();
  private readonly speaker = new VoiceSpeaker();

  private config: WidgetConfig | null = null;
  private token: string | null = null;
  private conversationId: string | null = null;
  private messages: WidgetMessage[] = [];
  private isOpen = false;
  private isStreaming = false;
  private isListening = false;
  private voiceOutputEnabled = false;
  private activeForm: FormKind = null;

  private launcherButton!: HTMLButtonElement;
  private panelEl!: HTMLDivElement;
  private transcriptEl!: HTMLDivElement;
  private composerInput!: HTMLTextAreaElement;
  private sendButton!: HTMLButtonElement;
  private micButton!: HTMLButtonElement | null;
  private voiceToggleButton!: HTMLButtonElement | null;
  private errorBannerEl!: HTMLDivElement;
  private suggestedEl!: HTMLDivElement;

  constructor(options: WidgetOptions, host: HTMLElement) {
    this.api = new WidgetApiClient({ apiBaseUrl: options.apiBaseUrl, publicId: options.publicId });
    this.publicId = options.publicId;
    this.visitorReference = options.visitorReference;
    this.sessionNamespace = options.sessionNamespace;
    this.host = host;
    this.shadow = host.attachShadow({ mode: "open" });
  }

  async mount(): Promise<void> {
    try {
      this.config = await this.api.getConfig();
    } catch {
      // Config fetch failure: render nothing rather than a broken widget —
      // the host page must never fail because of this (see docs/api.md's
      // installation-snippet contract).
      return;
    }
    this.renderShell();
    this.restoreStoredSessionIfAny();
  }

  destroy(): void {
    this.recognizer.abort();
    this.speaker.cancel();
    this.shadow.replaceChildren();
    this.host.remove();
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  private renderShell(): void {
    const config = this.config!;
    const style = el("style");
    style.textContent = buildStyles(config.accent_color || "#111111");
    this.shadow.appendChild(style);

    const positionClass = config.launcher_position === "bottom-left" ? "left" : "right";

    this.launcherButton = el("button", `launcher launcher--${positionClass}`, "💬");
    this.launcherButton.type = "button";
    this.launcherButton.setAttribute("aria-label", `Open chat with ${config.receptionist_name}`);
    this.launcherButton.addEventListener("click", () => this.togglePanel());
    this.shadow.appendChild(this.launcherButton);

    this.panelEl = el("div", `panel panel--${positionClass}`);
    this.panelEl.hidden = true;
    this.panelEl.setAttribute("role", "dialog");
    this.panelEl.setAttribute("aria-label", `Chat with ${config.receptionist_name}`);
    this.panelEl.addEventListener("keydown", (e) => {
      if (e.key === "Escape") this.togglePanel();
    });
    this.shadow.appendChild(this.panelEl);

    this.renderHeader();
    this.renderDisclosure();
    this.renderStatusLine();
    this.errorBannerEl = el("div", "error-banner");
    this.errorBannerEl.hidden = true;
    this.errorBannerEl.setAttribute("role", "alert");
    this.panelEl.appendChild(this.errorBannerEl);

    this.transcriptEl = el("div", "transcript");
    this.transcriptEl.setAttribute("role", "log");
    this.transcriptEl.setAttribute("aria-live", "polite");
    this.panelEl.appendChild(this.transcriptEl);

    this.suggestedEl = el("div", "suggested");
    this.panelEl.appendChild(this.suggestedEl);

    this.renderActionsRow();
    this.renderComposer();
  }

  private renderHeader(): void {
    const config = this.config!;
    const header = el("div", "header");
    const title = el("h1", undefined, config.business_name);
    if (config.mock_mode) {
      const badge = el("span", "badge", "Demo AI");
      badge.title = "Responses are generated by a deterministic, zero-cost demonstration engine — not a live external AI model.";
      title.appendChild(badge);
    }
    header.appendChild(title);

    const buttons = el("div", "header-buttons");
    const newConvoButton = el("button", "icon-button", "＋");
    newConvoButton.type = "button";
    newConvoButton.setAttribute("aria-label", "Start a new conversation");
    newConvoButton.addEventListener("click", () => void this.startNewConversation());
    buttons.appendChild(newConvoButton);

    const closeButton = el("button", "icon-button", "✕");
    closeButton.type = "button";
    closeButton.setAttribute("aria-label", "Close chat");
    closeButton.addEventListener("click", () => this.togglePanel());
    buttons.appendChild(closeButton);

    header.appendChild(buttons);
    this.panelEl.appendChild(header);
  }

  private renderDisclosure(): void {
    const config = this.config!;
    const disclosure = el("div", "disclosure", config.ai_disclosure);
    this.panelEl.appendChild(disclosure);
  }

  private renderStatusLine(): void {
    // Reused as a live region for transient status ("Listening…", errors handled separately).
    const status = el("div", "status-line visually-hidden");
    status.setAttribute("aria-live", "polite");
    status.id = "widget-status-line";
    this.panelEl.appendChild(status);
  }

  private setStatus(text: string): void {
    const node = this.shadow.getElementById("widget-status-line");
    if (node) node.textContent = text;
  }

  private renderActionsRow(): void {
    const row = el("div", "actions-row");

    const contactBtn = el("button", undefined, "Leave your contact info");
    contactBtn.type = "button";
    contactBtn.addEventListener("click", () => this.openForm("contact"));
    row.appendChild(contactBtn);

    const appointmentBtn = el("button", undefined, "Request an appointment");
    appointmentBtn.type = "button";
    appointmentBtn.addEventListener("click", () => this.openForm("appointment"));
    row.appendChild(appointmentBtn);

    const handoffBtn = el("button", undefined, "Talk to a human");
    handoffBtn.type = "button";
    handoffBtn.addEventListener("click", () => this.openForm("handoff"));
    row.appendChild(handoffBtn);

    this.panelEl.appendChild(row);
  }

  private renderComposer(): void {
    const config = this.config!;
    const composer = el("div", "composer");

    this.composerInput = el("textarea");
    this.composerInput.rows = 1;
    this.composerInput.placeholder = "Type a message…";
    this.composerInput.setAttribute("aria-label", "Message");
    this.composerInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void this.handleSend();
      }
    });
    composer.appendChild(this.composerInput);

    if (config.voice_enabled && isSpeechRecognitionSupported()) {
      this.micButton = el("button", "mic-button", "🎤");
      this.micButton.type = "button";
      this.micButton.setAttribute("aria-pressed", "false");
      this.micButton.setAttribute("aria-label", "Use voice input");
      this.micButton.addEventListener("click", () => this.toggleVoiceInput());
      composer.appendChild(this.micButton);
    }

    if (config.voice_enabled && isSpeechSynthesisSupported()) {
      this.voiceToggleButton = el("button", "voice-toggle", "🔈");
      this.voiceToggleButton.type = "button";
      this.voiceToggleButton.setAttribute("aria-pressed", "false");
      this.voiceToggleButton.setAttribute("aria-label", "Toggle spoken responses");
      this.voiceToggleButton.addEventListener("click", () => this.toggleVoiceOutput());
      composer.appendChild(this.voiceToggleButton);
    }

    this.sendButton = el("button", "send-button", "Send");
    this.sendButton.type = "button";
    this.sendButton.addEventListener("click", () => void this.handleSend());
    composer.appendChild(this.sendButton);

    this.panelEl.appendChild(composer);
    this.updateSuggestedQuestions();
  }

  private updateSuggestedQuestions(): void {
    this.suggestedEl.replaceChildren();
    if (this.messages.length > 0 || !this.config) return;
    for (const question of this.config.suggested_questions.slice(0, 4)) {
      const btn = el("button", undefined, question);
      btn.type = "button";
      btn.addEventListener("click", () => {
        this.composerInput.value = question;
        void this.handleSend();
      });
      this.suggestedEl.appendChild(btn);
    }
  }

  private showError(message: string): void {
    this.errorBannerEl.replaceChildren();
    this.errorBannerEl.appendChild(el("span", undefined, message));
    const retry = el("button", undefined, "Dismiss");
    retry.type = "button";
    retry.addEventListener("click", () => this.clearError());
    this.errorBannerEl.appendChild(retry);
    this.errorBannerEl.hidden = false;
  }

  private clearError(): void {
    this.errorBannerEl.hidden = true;
  }

  private renderMessage(message: WidgetMessage): void {
    const bubble = el("div", `bubble bubble--${message.role}`, message.content);
    this.transcriptEl.appendChild(bubble);
    this.transcriptEl.scrollTop = this.transcriptEl.scrollHeight;
  }

  // ------------------------------------------------------------------
  // Session / conversation lifecycle
  // ------------------------------------------------------------------

  private restoreStoredSessionIfAny(): void {
    const stored = loadStoredSession(this.publicId, this.sessionNamespace);
    if (stored) {
      this.token = stored.token;
      this.conversationId = stored.conversationId;
    }
  }

  private togglePanel(): void {
    this.isOpen = !this.isOpen;
    this.panelEl.hidden = !this.isOpen;
    if (this.isOpen) {
      this.launcherButton.setAttribute("aria-expanded", "true");
      void this.ensureConversationStarted();
      this.composerInput.focus();
    } else {
      this.launcherButton.setAttribute("aria-expanded", "false");
      this.recognizer.abort();
      this.isListening = false;
      this.speaker.cancel();
      // Without this, closing the panel (via the close button or Escape)
      // left focus on the now-hidden composer textarea — invisible to a
      // sighted keyboard user and unreachable by a screen reader, since a
      // `hidden` ancestor removes it from the accessibility tree. Restoring
      // focus to the launcher mirrors the panel's own entry behavior
      // (focus moves to the composer on open) and matches this codebase's
      // dialog-focus-restoration convention elsewhere (see
      // frontend/src/components/dashboard/ConfirmDialog.tsx).
      this.launcherButton.focus();
    }
  }

  private async ensureConversationStarted(): Promise<void> {
    if (this.conversationId && this.token) {
      if (this.messages.length === 0) {
        try {
          const detail = await this.api.getConversation(this.token, this.conversationId);
          this.messages = detail.messages;
          for (const m of this.messages) this.renderMessage(m);
          this.updateSuggestedQuestions();
          return;
        } catch {
          // Stored session no longer valid (expired/revoked) — fall through and start fresh.
          clearStoredSession(this.publicId, this.sessionNamespace);
          this.token = null;
          this.conversationId = null;
        }
      } else {
        return;
      }
    }
    await this.startFreshSession();
  }

  private async startFreshSession(): Promise<void> {
    try {
      const started = await this.api.startSession(this.visitorReference);
      this.token = started.capability_token;
      this.conversationId = started.conversation.id;
      saveStoredSession(
        this.publicId,
        { token: this.token, conversationId: this.conversationId },
        this.sessionNamespace
      );
      this.messages = [];
      this.transcriptEl.replaceChildren();
      if (this.config?.welcome_message) {
        const welcome = el("div", "bubble bubble--assistant", this.config.welcome_message);
        this.transcriptEl.appendChild(welcome);
      }
      this.updateSuggestedQuestions();
    } catch (err) {
      this.showError(this.friendlyErrorMessage(err));
    }
  }

  private async startNewConversation(): Promise<void> {
    if (!this.token) {
      await this.startFreshSession();
      return;
    }
    try {
      const started = await this.api.startNewConversation(this.token, this.visitorReference);
      this.token = started.capability_token;
      this.conversationId = started.conversation.id;
      saveStoredSession(
        this.publicId,
        { token: this.token, conversationId: this.conversationId },
        this.sessionNamespace
      );
      this.messages = [];
      this.transcriptEl.replaceChildren();
      this.updateSuggestedQuestions();
      this.clearError();
    } catch (err) {
      this.showError(this.friendlyErrorMessage(err));
    }
  }

  private friendlyErrorMessage(err: unknown): string {
    if (err instanceof WidgetApiError) {
      if (err.status === 429) return "You're sending messages too quickly. Please wait a moment and try again.";
      if (err.status === 409) return "This conversation is no longer available. Start a new conversation to continue.";
      // A 422 is a validation error the backend already wrote as safe,
      // actionable, user-facing text (e.g. "Requested date cannot be in
      // the past.") — never an internal/security-sensitive detail (see
      // app/services/*_service.py's *Error message strings). Showing it
      // directly, found worth doing during live verification: the generic
      // fallback below left a visitor with no way to tell *why* a
      // perfectly reasonable-looking date was rejected.
      if (err.status === 422 && err.message) return err.message;
      return "Something went wrong. Please try again.";
    }
    return "Something went wrong. Please check your connection and try again.";
  }

  // ------------------------------------------------------------------
  // Messaging
  // ------------------------------------------------------------------

  private async handleSend(): Promise<void> {
    const content = this.composerInput.value.trim();
    if (!content || this.isStreaming || !this.token || !this.conversationId) return;
    this.composerInput.value = "";
    this.clearError();
    this.isStreaming = true;
    this.sendButton.disabled = true;

    const userMessage: WidgetMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content,
      sequence_number: this.messages.length,
      citations: [],
      created_at: new Date().toISOString(),
    };
    this.messages.push(userMessage);
    this.renderMessage(userMessage);
    this.updateSuggestedQuestions();

    let accumulated = "";
    let assistantBubble: HTMLDivElement | null = null;

    try {
      for await (const event of this.api.sendMessage(this.token, this.conversationId, content, newIdempotencyKey())) {
        this.handleStreamEvent(event, {
          onDelta: (delta) => {
            accumulated += delta;
            if (!assistantBubble) {
              assistantBubble = el("div", "bubble bubble--assistant");
              this.transcriptEl.appendChild(assistantBubble);
            }
            assistantBubble.textContent = accumulated;
            this.transcriptEl.scrollTop = this.transcriptEl.scrollHeight;
          },
          onCompleted: (content2) => {
            if (this.voiceOutputEnabled) this.speaker.speak(content2, this.config?.supported_languages[0] || "en");
          },
        });
      }
    } catch (err) {
      this.showError(this.friendlyErrorMessage(err));
    } finally {
      this.isStreaming = false;
      this.sendButton.disabled = false;
    }
  }

  private handleStreamEvent(
    event: WidgetSSEEvent,
    handlers: { onDelta: (delta: string) => void; onCompleted: (content: string) => void }
  ): void {
    switch (event.event) {
      case "response.delta":
        handlers.onDelta(event.data.delta);
        break;
      case "response.completed":
        this.messages.push({
          id: event.data.message_id,
          role: "assistant",
          content: event.data.content,
          sequence_number: event.data.sequence_number,
          citations: [],
          created_at: new Date().toISOString(),
        });
        handlers.onCompleted(event.data.content);
        break;
      case "response.error":
        this.showError(event.data.message);
        break;
      default:
        break;
    }
  }

  // ------------------------------------------------------------------
  // Voice
  // ------------------------------------------------------------------

  private toggleVoiceInput(): void {
    if (!this.micButton) return;
    if (this.isListening) {
      this.recognizer.stop();
      return;
    }
    const locale = this.config?.supported_languages[0] || "en-US";
    this.isListening = true;
    this.micButton.setAttribute("aria-pressed", "true");
    this.setStatus("Listening…");
    this.recognizer.start(locale, {
      onResult: (transcript) => {
        this.composerInput.value = transcript;
        this.composerInput.focus();
      },
      onError: (reason: VoiceRecognitionErrorReason) => {
        this.isListening = false;
        this.micButton?.setAttribute("aria-pressed", "false");
        this.setStatus("");
        if (reason === "permission-denied") this.showError("Microphone access was denied. You can still type your message.");
        else if (reason === "not-supported") this.showError("Voice input isn't supported in this browser. Please type your message.");
        else if (reason === "no-speech") this.setStatus("No speech detected.");
      },
      onEnd: () => {
        this.isListening = false;
        this.micButton?.setAttribute("aria-pressed", "false");
        this.setStatus("");
      },
    });
  }

  private toggleVoiceOutput(): void {
    if (!this.voiceToggleButton) return;
    this.voiceOutputEnabled = !this.voiceOutputEnabled;
    this.speaker.setEnabled(this.voiceOutputEnabled);
    this.voiceToggleButton.setAttribute("aria-pressed", String(this.voiceOutputEnabled));
    this.voiceToggleButton.textContent = this.voiceOutputEnabled ? "🔊" : "🔈";
  }

  // ------------------------------------------------------------------
  // Structured action forms (contact / appointment / handoff)
  // ------------------------------------------------------------------

  private openForm(kind: FormKind): void {
    if (this.activeForm) {
      // One structured action form at a time — prevents stacked overlays
      // if a button is clicked twice in quick succession.
      return;
    }
    this.activeForm = kind;
    const overlay = el("div", "form-overlay");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-label", `${kind} form`);

    // A form-local error slot, deliberately separate from the main
    // conversation error banner: that banner lives earlier in `panelEl`
    // and this overlay covers it completely (`.form-overlay` is
    // `position: absolute; inset: 0`), so a validation error shown via
    // `showError` while a form is open would be invisible to the visitor.
    const formError = el("p", "form-error");
    formError.setAttribute("role", "alert");
    formError.hidden = true;

    if (kind === "contact") this.buildContactForm(overlay, formError);
    else if (kind === "appointment") this.buildAppointmentForm(overlay, formError);
    else if (kind === "handoff") this.buildHandoffForm(overlay, formError);

    this.panelEl.appendChild(overlay);
  }

  private closeForm(overlay: HTMLElement): void {
    overlay.remove();
    this.activeForm = null;
  }

  private showFormError(formError: HTMLParagraphElement, message: string): void {
    formError.textContent = message;
    formError.hidden = false;
  }

  private buildContactForm(overlay: HTMLDivElement, formError: HTMLParagraphElement): void {
    overlay.appendChild(el("h2", undefined, "Leave your contact info"));
    overlay.appendChild(
      el("p", undefined, "We'll use this only to follow up on your enquiry. Sharing your details is optional.")
    );
    overlay.appendChild(formError);

    const nameLabel = el("label", undefined, "Name");
    const nameInput = el("input");
    nameInput.type = "text";
    nameLabel.appendChild(nameInput);

    const emailLabel = el("label", undefined, "Email");
    const emailInput = el("input");
    emailInput.type = "email";
    emailLabel.appendChild(emailInput);

    const phoneLabel = el("label", undefined, "Phone");
    const phoneInput = el("input");
    phoneInput.type = "tel";
    phoneLabel.appendChild(phoneInput);

    const consentLabel = el("label", "consent-row");
    const consentInput = el("input");
    consentInput.type = "checkbox";
    consentInput.checked = false;
    consentLabel.appendChild(consentInput);
    consentLabel.appendChild(document.createTextNode("I'd also like to receive occasional marketing updates (optional)"));

    overlay.append(nameLabel, emailLabel, phoneLabel, consentLabel);

    const buttons = el("div", "form-buttons");
    const cancelBtn = el("button", undefined, "Cancel");
    cancelBtn.type = "button";
    cancelBtn.addEventListener("click", () => this.closeForm(overlay));
    const submitBtn = el("button", "primary", "Submit");
    submitBtn.type = "button";
    submitBtn.addEventListener("click", () => {
      void (async () => {
        if (!this.token) return;
        if (!nameInput.value && !emailInput.value && !phoneInput.value) {
          this.showFormError(formError, "Please provide at least a name, email, or phone number.");
          return;
        }
        try {
          await this.api.submitContact(this.token, {
            name: nameInput.value || undefined,
            email: emailInput.value || undefined,
            phone: phoneInput.value || undefined,
            marketing_consent: consentInput.checked,
          });
          this.closeForm(overlay);
          this.renderMessage({
            id: `local-ack-${Date.now()}`,
            role: "assistant",
            content: "Thanks — your contact details have been received.",
            sequence_number: this.messages.length,
            citations: [],
            created_at: new Date().toISOString(),
          });
        } catch (err) {
          this.showFormError(formError, this.friendlyErrorMessage(err));
        }
      })();
    });
    buttons.append(cancelBtn, submitBtn);
    overlay.appendChild(buttons);
  }

  private buildAppointmentForm(overlay: HTMLDivElement, formError: HTMLParagraphElement): void {
    overlay.appendChild(el("h2", undefined, "Request an appointment"));
    overlay.appendChild(
      el(
        "p",
        undefined,
        "This is an appointment request, pending confirmation — the business will confirm availability and follow up with you."
      )
    );
    overlay.appendChild(formError);

    const dateLabel = el("label", undefined, "Preferred date");
    const dateInput = el("input");
    dateInput.type = "date";
    dateLabel.appendChild(dateInput);

    const windowLabel = el("label", undefined, "Preferred time of day");
    const windowSelect = el("select");
    for (const opt of ["Morning", "Afternoon", "Evening"]) {
      const option = el("option", undefined, opt);
      option.value = opt.toLowerCase();
      windowSelect.appendChild(option);
    }
    windowLabel.appendChild(windowSelect);

    // Service/location pickers only appear when the tenant has configured
    // at least one active record of that kind — an empty <select> with
    // only "Not sure" would add a step for no benefit. Neither selector
    // claims real-time availability; picking one only tells the business
    // which service/location the visitor has in mind.
    const services = this.config?.services ?? [];
    const locations = this.config?.locations ?? [];

    let serviceSelect: HTMLSelectElement | null = null;
    if (services.length > 0) {
      const serviceLabel = el("label", undefined, "Service (optional)");
      serviceSelect = el("select");
      serviceSelect.appendChild(new Option("Not sure", ""));
      for (const service of services) {
        serviceSelect.appendChild(new Option(service.name, service.id));
      }
      serviceLabel.appendChild(serviceSelect);
      overlay.appendChild(serviceLabel);
    }

    let locationSelect: HTMLSelectElement | null = null;
    if (locations.length > 0) {
      const locationLabel = el("label", undefined, "Location (optional)");
      locationSelect = el("select");
      locationSelect.appendChild(new Option("Not sure", ""));
      for (const location of locations) {
        locationSelect.appendChild(new Option(location.name, location.id));
      }
      locationLabel.appendChild(locationSelect);
      overlay.appendChild(locationLabel);
    }

    const notesLabel = el("label", undefined, "Notes (optional)");
    const notesInput = el("textarea");
    notesLabel.appendChild(notesInput);

    overlay.append(dateLabel, windowLabel, notesLabel);

    const buttons = el("div", "form-buttons");
    const cancelBtn = el("button", undefined, "Cancel");
    cancelBtn.type = "button";
    cancelBtn.addEventListener("click", () => this.closeForm(overlay));
    const submitBtn = el("button", "primary", "Submit request");
    submitBtn.type = "button";
    submitBtn.addEventListener("click", () => {
      void (async () => {
        if (!this.token || !dateInput.value) {
          this.showFormError(formError, "Please choose a preferred date.");
          return;
        }
        const selectedLocationId = locationSelect?.value || undefined;
        const selectedLocation = locations.find((loc) => loc.id === selectedLocationId);
        // A selected location's own timezone governs the date boundary
        // server-side (see docs/security.md) — sending it explicitly here,
        // rather than only the browser's local timezone, keeps the
        // visitor-facing date picker and the server's validation reasoning
        // about the same "today".
        const timezone = selectedLocation?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
        try {
          const result = await this.api.submitAppointmentRequest(this.token, {
            requested_date: dateInput.value,
            requested_time_window: windowSelect.value,
            timezone,
            notes: notesInput.value || undefined,
            idempotency_key: newIdempotencyKey(),
            service_id: serviceSelect?.value || undefined,
            location_id: selectedLocationId,
          });
          this.closeForm(overlay);
          this.renderMessage({
            id: `local-ack-${Date.now()}`,
            role: "assistant",
            content: result.message,
            sequence_number: this.messages.length,
            citations: [],
            created_at: new Date().toISOString(),
          });
        } catch (err) {
          this.showFormError(formError, this.friendlyErrorMessage(err));
        }
      })();
    });
    buttons.append(cancelBtn, submitBtn);
    overlay.appendChild(buttons);
  }

  private buildHandoffForm(overlay: HTMLDivElement, formError: HTMLParagraphElement): void {
    overlay.appendChild(el("h2", undefined, "Talk to a human"));
    overlay.appendChild(
      el("p", undefined, "A team member will follow up with you during business hours. This does not connect you immediately.")
    );
    overlay.appendChild(formError);

    const reasonLabel = el("label", undefined, "What can we help with?");
    const reasonInput = el("textarea");
    reasonLabel.appendChild(reasonInput);

    overlay.append(reasonLabel);

    const buttons = el("div", "form-buttons");
    const cancelBtn = el("button", undefined, "Cancel");
    cancelBtn.type = "button";
    cancelBtn.addEventListener("click", () => this.closeForm(overlay));
    const submitBtn = el("button", "primary", "Request callback");
    submitBtn.type = "button";
    submitBtn.addEventListener("click", () => {
      void (async () => {
        if (!this.token || !reasonInput.value.trim()) {
          this.showFormError(formError, "Please describe what you'd like help with.");
          return;
        }
        try {
          const result = await this.api.submitHandoffRequest(this.token, {
            reason: reasonInput.value.trim(),
            idempotency_key: newIdempotencyKey(),
          });
          this.closeForm(overlay);
          this.renderMessage({
            id: `local-ack-${Date.now()}`,
            role: "assistant",
            content: result.message,
            sequence_number: this.messages.length,
            citations: [],
            created_at: new Date().toISOString(),
          });
        } catch (err) {
          this.showFormError(formError, this.friendlyErrorMessage(err));
        }
      })();
    });
    buttons.append(cancelBtn, submitBtn);
    overlay.appendChild(buttons);
  }
}
