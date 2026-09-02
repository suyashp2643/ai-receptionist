// jsdom implements no part of the Web Speech API — polyfill just enough of
// speechSynthesis/SpeechSynthesisUtterance for tests to exercise
// VoiceSpeaker's real logic (cancel-before-speak, enable/disable) against
// something, without pulling in a real speech engine (there isn't one to
// pull in for a zero-cost test suite).
if (typeof window !== "undefined" && !("speechSynthesis" in window)) {
  (window as unknown as Record<string, unknown>).speechSynthesis = {
    cancel: () => {},
    speak: () => {},
    getVoices: () => [],
  };
}
if (typeof window !== "undefined" && !("SpeechSynthesisUtterance" in window)) {
  (window as unknown as Record<string, unknown>).SpeechSynthesisUtterance = class {
    text: string;
    lang = "";
    constructor(text: string) {
      this.text = text;
    }
  };
}
