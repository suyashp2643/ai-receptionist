"use client";

import { useState } from "react";
import { exportCsv, type ExportEntity, type ExportFilters } from "@/lib/dashboard-api";
import { ApiError } from "@/lib/api";

/** Owner/admin-only CSV export for one entity, scoped to the page's own
 * currently-active date range (and status/source filter, where the
 * backend contract supports it — see app/services/export_service.py).
 * Downloads directly via the browser's own object-URL mechanism; the file
 * is never persisted anywhere by this app beyond the visitor's own
 * download. Renders nothing for a member — export is owner/admin-only. */
export function ExportButton({
  tenantId,
  entity,
  canManage,
  dateFrom,
  dateTo,
  statuses,
  sources,
}: {
  tenantId: string;
  entity: ExportEntity;
  canManage: boolean;
  dateFrom: string;
  dateTo: string;
  statuses?: string[];
  sources?: string[];
}) {
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!canManage) return null;

  async function handleExport() {
    setState("loading");
    setErrorMessage(null);
    try {
      const filters: ExportFilters = { statuses, sources };
      const blob = await exportCsv(tenantId, entity, dateFrom, dateTo, filters);
      // Filename mirrors the backend's own Content-Disposition convention
      // (entity + date range) — safe because dateFrom/dateTo are always
      // ISO `YYYY-MM-DD` strings from a <input type="date">, never
      // free-form user text.
      const filename = `${entity}_${dateFrom}_${dateTo}.csv`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setState("success");
      setTimeout(() => setState((s) => (s === "success" ? "idle" : s)), 2500);
    } catch (err) {
      setState("error");
      setErrorMessage(err instanceof ApiError ? err.message : "Could not export this data.");
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={handleExport}
        disabled={state === "loading"}
        className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
      >
        {state === "loading" ? "Exporting…" : "Export CSV"}
      </button>
      {state === "success" && (
        <span className="text-xs text-green-700 dark:text-green-400" role="status">
          Downloaded
        </span>
      )}
      {state === "error" && (
        <span className="text-xs text-red-600 dark:text-red-400" role="alert">
          {errorMessage}
        </span>
      )}
    </div>
  );
}
