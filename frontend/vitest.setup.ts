import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// RTL's automatic cleanup only self-registers when it detects Jest-style
// globals; this project uses explicit `import { afterEach } from "vitest"`
// instead, so cleanup is wired up explicitly here — without this, DOM from
// one test's render() leaks into the next test in the same file.
afterEach(() => {
  cleanup();
});

// jsdom does not implement scrollIntoView at all — components that call it
// (e.g. auto-scrolling a transcript to the latest message) throw in tests
// otherwise. A no-op is all any test needs.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
