"use client";

import { useEffect, useState } from "react";
import { getApiBaseUrl } from "@/lib/config";

type DatabaseHealth = {
  status: string;
  detail: string;
};

type HealthResponse = {
  status: string;
  service: string;
  environment: string;
  database: DatabaseHealth;
};

type FetchState =
  | { phase: "loading" }
  | { phase: "success"; data: HealthResponse }
  | { phase: "error"; message: string };

export function ApiHealthStatus() {
  const [state, setState] = useState<FetchState>({ phase: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function check() {
      try {
        const response = await fetch(`${getApiBaseUrl()}/api/v1/health`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Backend responded with status ${response.status}`);
        }
        const data = (await response.json()) as HealthResponse;
        setState({ phase: "success", data });
      } catch (error) {
        if (controller.signal.aborted) return;
        const message =
          error instanceof Error ? error.message : "Unable to reach the backend API";
        setState({ phase: "error", message });
      }
    }

    check();
    return () => controller.abort();
  }, []);

  return (
    <div className="w-full max-w-md rounded-lg border border-black/10 dark:border-white/15 p-4 text-sm">
      <p className="font-medium mb-2">Backend API status</p>
      {state.phase === "loading" && <p className="text-neutral-500">Checking…</p>}
      {state.phase === "error" && (
        <div className="text-red-600 dark:text-red-400">
          <p>Unreachable</p>
          <p className="text-xs opacity-80 mt-1">{state.message}</p>
        </div>
      )}
      {state.phase === "success" && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-neutral-500">Overall</dt>
          <dd className={state.data.status === "ok" ? "text-green-600" : "text-amber-600"}>
            {state.data.status}
          </dd>
          <dt className="text-neutral-500">Service</dt>
          <dd>{state.data.service}</dd>
          <dt className="text-neutral-500">Environment</dt>
          <dd>{state.data.environment}</dd>
          <dt className="text-neutral-500">Database</dt>
          <dd>
            {state.data.database.status} — {state.data.database.detail}
          </dd>
        </dl>
      )}
    </div>
  );
}
