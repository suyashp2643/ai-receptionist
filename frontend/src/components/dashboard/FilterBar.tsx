"use client";

import type { AnalyticsPreset } from "@/lib/dashboard-api";

export interface Receptionist {
  id: string;
  name: string;
}

export function AnalyticsFilterBar({
  preset,
  onPresetChange,
  customStart,
  customEnd,
  onCustomStartChange,
  onCustomEndChange,
  receptionistId,
  onReceptionistChange,
  receptionists,
  includeTestPreview,
  onIncludeTestPreviewChange,
}: {
  preset: AnalyticsPreset;
  onPresetChange: (p: AnalyticsPreset) => void;
  customStart: string;
  customEnd: string;
  onCustomStartChange: (v: string) => void;
  onCustomEndChange: (v: string) => void;
  receptionistId: string;
  onReceptionistChange: (v: string) => void;
  receptionists: Receptionist[];
  includeTestPreview: boolean;
  onIncludeTestPreviewChange: (v: boolean) => void;
}) {
  return (
    <div className="rounded-lg border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 p-3 flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1">
        <label htmlFor="analytics-preset" className="text-xs text-neutral-500">
          Date range
        </label>
        <select
          id="analytics-preset"
          value={preset}
          onChange={(e) => onPresetChange(e.target.value as AnalyticsPreset)}
          className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="today">Today</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="custom">Custom range</option>
        </select>
      </div>

      {preset === "custom" && (
        <>
          <div className="flex flex-col gap-1">
            <label htmlFor="analytics-custom-start" className="text-xs text-neutral-500">
              From
            </label>
            <input
              id="analytics-custom-start"
              type="date"
              value={customStart}
              onChange={(e) => onCustomStartChange(e.target.value)}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="analytics-custom-end" className="text-xs text-neutral-500">
              To
            </label>
            <input
              id="analytics-custom-end"
              type="date"
              value={customEnd}
              onChange={(e) => onCustomEndChange(e.target.value)}
              className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
            />
          </div>
        </>
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor="analytics-receptionist" className="text-xs text-neutral-500">
          Receptionist
        </label>
        <select
          id="analytics-receptionist"
          value={receptionistId}
          onChange={(e) => onReceptionistChange(e.target.value)}
          className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="">All receptionists</option>
          {receptionists.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </div>

      <label className="flex items-center gap-2 text-sm pb-1.5">
        <input
          type="checkbox"
          checked={includeTestPreview}
          onChange={(e) => onIncludeTestPreviewChange(e.target.checked)}
        />
        Include test &amp; preview traffic
      </label>
    </div>
  );
}
