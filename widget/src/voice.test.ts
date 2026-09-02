import { afterEach, describe, expect, it, vi } from "vitest";
import { isSpeechRecognitionSupported, isSpeechSynthesisSupported, VoiceRecognizer, VoiceSpeaker } from "./voice";

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).SpeechRecognition;
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  vi.restoreAllMocks();
});

describe("feature detection", () => {
  it("reports unsupported when no SpeechRecognition constructor exists", () => {
    expect(isSpeechRecognitionSupported()).toBe(false);
  });

  it("reports supported via the webkit-prefixed constructor", () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = class {};
    expect(isSpeechRecognitionSupported()).toBe(true);
  });

  it("reports speechSynthesis support based on window", () => {
    expect(isSpeechSynthesisSupported()).toBe(typeof window.speechSynthesis !== "undefined");
  });
});

class FakeRecognition extends EventTarget {
  lang = "";
  continuous = false;
  interimResults = false;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  started = false;

  start(): void {
    this.started = true;
  }
  stop(): void {
    this.onend?.();
  }
  abort(): void {
    this.onend?.();
  }
}

describe("VoiceRecognizer", () => {
  it("calls onError with not-supported when no constructor exists", () => {
    const recognizer = new VoiceRecognizer();
    const onError = vi.fn();
    const started = recognizer.start("en-US", { onResult: vi.fn(), onError, onEnd: vi.fn() });
    expect(started).toBe(false);
    expect(onError).toHaveBeenCalledWith("not-supported");
  });

  it("prevents a second simultaneous recognizer from starting", () => {
    let constructedCount = 0;
    (window as unknown as Record<string, unknown>).SpeechRecognition = class extends FakeRecognition {
      constructor() {
        super();
        constructedCount += 1;
      }
    };
    const recognizer = new VoiceRecognizer();
    const first = recognizer.start("en-US", { onResult: vi.fn(), onError: vi.fn(), onEnd: vi.fn() });
    const second = recognizer.start("en-US", { onResult: vi.fn(), onError: vi.fn(), onEnd: vi.fn() });
    expect(first).toBe(true);
    expect(second).toBe(false);
    expect(constructedCount).toBe(1);
  });

  it("maps a not-allowed error to permission-denied", () => {
    (window as unknown as Record<string, unknown>).SpeechRecognition = FakeRecognition;
    const recognizer = new VoiceRecognizer();
    const onError = vi.fn();
    recognizer.start("en-US", { onResult: vi.fn(), onError, onEnd: vi.fn() });
    const active = (recognizer as unknown as { recognition: FakeRecognition }).recognition;
    active.onerror?.({ error: "not-allowed" });
    expect(onError).toHaveBeenCalledWith("permission-denied");
  });

  it("becomes inactive again after stop() fires onend", () => {
    (window as unknown as Record<string, unknown>).SpeechRecognition = FakeRecognition;
    const recognizer = new VoiceRecognizer();
    recognizer.start("en-US", { onResult: vi.fn(), onError: vi.fn(), onEnd: vi.fn() });
    expect(recognizer.isActive).toBe(true);
    recognizer.stop();
    expect(recognizer.isActive).toBe(false);
  });
});

describe("VoiceSpeaker", () => {
  it("does not speak when disabled", () => {
    const speaker = new VoiceSpeaker();
    const spy = vi.spyOn(window.speechSynthesis, "speak").mockImplementation(() => {});
    speaker.speak("hello", "en-US");
    expect(spy).not.toHaveBeenCalled();
  });

  it("cancels any previous utterance before speaking a new one", () => {
    const speaker = new VoiceSpeaker();
    speaker.setEnabled(true);
    const cancelSpy = vi.spyOn(window.speechSynthesis, "cancel").mockImplementation(() => {});
    const speakSpy = vi.spyOn(window.speechSynthesis, "speak").mockImplementation(() => {});
    speaker.speak("hello", "en-US");
    expect(cancelSpy).toHaveBeenCalled();
    expect(speakSpy).toHaveBeenCalled();
  });

  it("cancels speech when disabled", () => {
    const speaker = new VoiceSpeaker();
    speaker.setEnabled(true);
    const cancelSpy = vi.spyOn(window.speechSynthesis, "cancel").mockImplementation(() => {});
    speaker.setEnabled(false);
    expect(cancelSpy).toHaveBeenCalled();
  });
});
