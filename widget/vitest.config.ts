import { defineConfig } from "vitest/config";

// Zero-cost, local-only test runner — no external services required.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    setupFiles: ["./vitest.setup.ts"],
  },
});
