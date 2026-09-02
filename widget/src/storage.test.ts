import { describe, expect, it, beforeEach } from "vitest";
import { clearStoredSession, loadStoredSession, saveStoredSession } from "./storage";

describe("widget session storage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("round-trips a saved session", () => {
    saveStoredSession("pub-1", { token: "tok-abc", conversationId: "conv-1" });
    expect(loadStoredSession("pub-1")).toEqual({ token: "tok-abc", conversationId: "conv-1" });
  });

  it("returns null when nothing is stored", () => {
    expect(loadStoredSession("pub-unknown")).toBeNull();
  });

  it("scopes storage per public id", () => {
    saveStoredSession("pub-1", { token: "tok-1", conversationId: "conv-1" });
    saveStoredSession("pub-2", { token: "tok-2", conversationId: "conv-2" });
    expect(loadStoredSession("pub-1")?.token).toBe("tok-1");
    expect(loadStoredSession("pub-2")?.token).toBe("tok-2");
  });

  it("clears a stored session", () => {
    saveStoredSession("pub-1", { token: "tok-abc", conversationId: "conv-1" });
    clearStoredSession("pub-1");
    expect(loadStoredSession("pub-1")).toBeNull();
  });

  it("returns null for malformed stored JSON instead of throwing", () => {
    window.sessionStorage.setItem("ai-receptionist-widget:pub-1", "not json");
    expect(loadStoredSession("pub-1")).toBeNull();
  });

  it("degrades to a no-op when sessionStorage throws", () => {
    const original = window.sessionStorage.setItem;
    window.sessionStorage.setItem = () => {
      throw new Error("storage disabled");
    };
    expect(() => saveStoredSession("pub-1", { token: "t", conversationId: "c" })).not.toThrow();
    window.sessionStorage.setItem = original;
  });
});
