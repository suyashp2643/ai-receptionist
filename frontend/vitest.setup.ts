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
