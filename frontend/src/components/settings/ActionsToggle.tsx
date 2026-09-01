"use client";

import { useEffect, useState } from "react";
import { ALLOWED_ACTIONS, getWorkflow, listReceptionists, updateWorkflow } from "@/lib/phase3-api";
import { ACTION_LABELS } from "@/lib/constants";
import { buttonClass, errorMessage, FieldError, SavedNotice } from "./shared";

export function ActionsToggle({ tenantId, canEdit }: { tenantId: string; canEdit: boolean }) {
  const [receptionistId, setReceptionistId] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const receptionists = await listReceptionists(tenantId);
        const receptionist = receptionists[0];
        if (!receptionist) {
          setIsLoading(false);
          return;
        }
        setReceptionistId(receptionist.id);
        const workflow = await getWorkflow(tenantId, receptionist.id);
        setEnabled(new Set(workflow.enabled_actions));
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setIsLoading(false);
      }
    })();
  }, [tenantId]);

  function toggle(action: string) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(action)) next.delete(action);
      else next.add(action);
      return next;
    });
  }

  async function handleSave() {
    if (!receptionistId) return;
    setError(null);
    setSaved(false);
    setIsSaving(true);
    try {
      await updateWorkflow(tenantId, receptionistId, { enabled_actions: Array.from(enabled) });
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <p className="text-neutral-500 text-sm">Loading…</p>;
  if (!receptionistId) {
    return <p className="text-sm text-neutral-500">Create a receptionist first to configure actions.</p>;
  }

  return (
    <div className="flex flex-col gap-4 max-w-lg">
      <FieldError message={error} />
      <ul className="flex flex-col gap-2">
        {ALLOWED_ACTIONS.map((action) => (
          <li key={action}>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                disabled={!canEdit}
                checked={enabled.has(action)}
                onChange={() => toggle(action)}
              />
              {ACTION_LABELS[action] ?? action}
            </label>
          </li>
        ))}
      </ul>
      {canEdit && (
        <div className="flex items-center gap-3">
          <button type="button" onClick={handleSave} disabled={isSaving} className={buttonClass}>
            {isSaving ? "Saving…" : "Save"}
          </button>
          <SavedNotice show={saved} />
        </div>
      )}
    </div>
  );
}
