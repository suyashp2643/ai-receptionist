import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

// Zero-cost, local-only test runner — no external services required. Uses
// jsdom so component tests can render without a real browser.
export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    // `fileParallelism: false` is deliberate, not a workaround for a test
    // bug — root-caused live (see docs/PROGRESS.md's Phase 6 follow-up):
    // Vitest's default `forks` pool spawns one worker process per CPU
    // core (6 were observed on this machine's reported 12 cores) to run
    // test FILES concurrently. Every RTL/jest-dom hygiene check passed —
    // global `afterEach(cleanup())` is wired in vitest.setup.ts, no test
    // mutates `global.fetch`, no test leaves fake timers active, no test
    // touches `process.env` or browser storage across files, and Vitest's
    // own `isolate: true` default already gives every file a fresh module
    // registry. The actual cause is memory, not test hygiene: this
    // environment has only ~3.5GB of total RAM, and live monitoring
    // during a real `vitest run` showed each of the 6 concurrent fork
    // workers growing from ~90MB to ~190MB of RSS within 24 seconds (a
    // worker keeps running further test files after finishing one, and
    // does not release jsdom/React/module memory back to the OS between
    // them) — available memory fell from ~2.9GB to ~1.4GB in that same
    // window, on a clear trajectory to exhaustion for a full run. Under
    // that memory pressure, V8's garbage collector pauses long enough
    // that isolated async operations (e.g. a `waitFor` inside one test)
    // occasionally exceed the default 5000ms per-test timeout — this is
    // exactly what was observed, reproducibly, in both this project's own
    // new Phase 6 tests and in an untouched Phase 3 file
    // (QualificationEditor.test.tsx), which is itself evidence the cause
    // is systemic rather than a defect in any specific test. Sequential
    // (single-process) execution keeps memory bounded to what one worker
    // uses; 109/109 tests then pass consistently (verified across 20
    // repeated runs — see docs/PROGRESS.md). This is the one test
    // configuration `npm test`, `npm run test:run`, and plain `vitest`/
    // `vitest run` all resolve to — there is no separate parallel mode
    // left active anywhere in this project.
    fileParallelism: false,
  },
});
