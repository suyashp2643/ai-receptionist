/**
 * Browser-native voice only — no server-side audio processing, no audio
 * upload endpoint, ever. STT uses the Web Speech API's SpeechRecognition
 * (vendor-prefixed on Chrome/Edge as webkitSpeechRecognition); TTS uses
 * speechSynthesis. Only the resulting *text* transcript is ever sent to the
 * backend (via the normal message-send call) — raw audio never leaves the
 * browser and is never stored, matching the "no raw audio storage"
 * requirement documented in docs/security.md.
 *
 * This module makes no claim about *where* the browser/OS actually does
 * speech processing (on-device vs. a vendor's cloud service) — that is up
 * to the browser/platform, not something this widget can verify or
 * control, and the UI must not claim "local-only processing".
 */

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onend: (() => void) | null;
}

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition as SpeechRecognitionCtor) || (w.webkitSpeechRecognition as SpeechRecognitionCtor) || null;
}

export function isSpeechRecognitionSupported(): boolean {
  return typeof window !== "undefined" && getSpeechRecognitionCtor() !== null;
}

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export type VoiceRecognitionErrorReason = "not-supported" | "permission-denied" | "no-speech" | "network" | "aborted" | "unknown";

export interface VoiceRecognitionHandlers {
  onResult: (transcript: string) => void;
  onError: (reason: VoiceRecognitionErrorReason) => void;
  onEnd: () => void;
}

/**
 * Wraps a single SpeechRecognition instance. Only one may run at a time
 * process-wide (see `isActive`) — the UI layer must check this before
 * calling `start()` to prevent two overlapping recognizers, which browsers
 * handle inconsistently (some throw, some silently abort the first).
 */
export class VoiceRecognizer {
  private recognition: SpeechRecognitionLike | null = null;
  private active = false;

  get isActive(): boolean {
    return this.active;
  }

  start(locale: string, handlers: VoiceRecognitionHandlers): boolean {
    if (this.active) return false;
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      handlers.onError("not-supported");
      return false;
    }

    const recognition = new Ctor();
    recognition.lang = locale;
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onresult = (event: unknown) => {
      const results = (event as { results?: ArrayLike<ArrayLike<{ transcript: string }>> }).results;
      const transcript = results && results[0] && results[0][0] ? results[0][0].transcript : "";
      if (transcript) handlers.onResult(transcript);
    };
    recognition.onerror = (event: unknown) => {
      const error = (event as { error?: string }).error ?? "unknown";
      const reason: VoiceRecognitionErrorReason =
        error === "not-allowed" || error === "service-not-allowed"
          ? "permission-denied"
          : error === "no-speech"
            ? "no-speech"
            : error === "network"
              ? "network"
              : error === "aborted"
                ? "aborted"
                : "unknown";
      handlers.onError(reason);
    };
    recognition.onend = () => {
      this.active = false;
      this.recognition = null;
      handlers.onEnd();
    };

    this.recognition = recognition;
    this.active = true;
    try {
      recognition.start();
    } catch {
      this.active = false;
      this.recognition = null;
      handlers.onError("unknown");
      return false;
    }
    return true;
  }

  stop(): void {
    this.recognition?.stop();
  }

  abort(): void {
    this.recognition?.abort();
    this.active = false;
    this.recognition = null;
  }
}

/**
 * Wraps speechSynthesis. `speak` always cancels any previous utterance
 * first — the app never queues overlapping speech. Never reads citations
 * or other metadata, only the plain response text the caller passes in.
 */
export class VoiceSpeaker {
  private enabled = false;

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    if (!enabled) this.cancel();
  }

  get isEnabled(): boolean {
    return this.enabled;
  }

  speak(text: string, locale: string): void {
    if (!this.enabled || !isSpeechSynthesisSupported() || !text) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = locale;
    window.speechSynthesis.speak(utterance);
  }

  cancel(): void {
    if (isSpeechSynthesisSupported()) window.speechSynthesis.cancel();
  }
}
