"use client";

import { useEffect, useState } from "react";
import {
  getOnboardingState,
  IndustryTemplateSummary,
  listIndustryTemplates,
  selectIndustry,
} from "@/lib/phase3-api";
import { errorMessage, FieldError } from "./shared";

export function IndustrySelector({
  tenantId,
  canEdit,
  onSelected,
}: {
  tenantId: string;
  canEdit: boolean;
  onSelected?: () => void;
}) {
  const [templates, setTemplates] = useState<IndustryTemplateSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [list, state] = await Promise.all([listIndustryTemplates(), getOnboardingState(tenantId)]);
        setTemplates(list);
        setSelectedId(state.business_profile?.industry_template_id ?? null);
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setIsLoading(false);
      }
    })();
  }, [tenantId]);

  async function handleSelect(key: string, id: string) {
    if (!canEdit) return;
    setError(null);
    setIsSaving(true);
    try {
      await selectIndustry(tenantId, key);
      setSelectedId(id);
      onSelected?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <p className="text-neutral-500 text-sm">Loading…</p>;

  return (
    <div className="flex flex-col gap-4">
      <FieldError message={error} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {templates.map((template) => {
          const isSelected = template.id === selectedId;
          return (
            <button
              key={template.id}
              type="button"
              disabled={!canEdit || isSaving}
              onClick={() => handleSelect(template.key, template.id)}
              className={`text-left rounded-lg border p-4 disabled:opacity-50 ${
                isSelected
                  ? "border-foreground bg-black/5 dark:bg-white/10"
                  : "border-black/10 dark:border-white/15"
              }`}
              aria-pressed={isSelected}
            >
              <p className="font-medium">{template.name}</p>
              <p className="text-sm text-neutral-500 mt-1">{template.description}</p>
              {isSelected && <p className="text-xs mt-2 text-foreground">Selected</p>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
