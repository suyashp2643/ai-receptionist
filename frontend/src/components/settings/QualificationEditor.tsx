"use client";

import { useEffect, useState } from "react";
import {
  getWorkflow,
  listReceptionists,
  QualificationField,
  updateWorkflow,
} from "@/lib/phase3-api";
import { QUALIFICATION_FIELD_TYPES } from "@/lib/constants";
import {
  addOption,
  applyFieldTypeChange,
  isSelectType,
  removeOption,
  reorderOptions,
  updateOption,
  validateQualificationField,
} from "@/lib/qualification-utils";
import {
  buttonClass,
  dangerButtonClass,
  errorMessage,
  FieldError,
  inputClass,
  secondaryButtonClass,
  SavedNotice,
} from "./shared";

export function QualificationEditor({ tenantId, canEdit }: { tenantId: string; canEdit: boolean }) {
  const [receptionistId, setReceptionistId] = useState<string | null>(null);
  const [fields, setFields] = useState<QualificationField[]>([]);
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
        setFields(workflow.qualification_schema.fields ?? []);
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setIsLoading(false);
      }
    })();
  }, [tenantId]);

  function addField() {
    setFields((prev) => [
      ...prev,
      {
        key: `field_${prev.length + 1}`,
        label: "New field",
        type: "short_text",
        required: false,
        display_order: prev.length,
        is_sensitive: false,
      },
    ]);
  }

  function updateField(index: number, patch: Partial<QualificationField>) {
    setFields((prev) => prev.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  }

  function handleTypeChange(index: number, newType: string) {
    setFields((prev) => prev.map((f, i) => (i === index ? applyFieldTypeChange(f, newType) : f)));
  }

  function removeField(index: number) {
    setFields((prev) => prev.filter((_, i) => i !== index));
  }

  function moveField(index: number, direction: -1 | 1) {
    setFields((prev) => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((f, i) => ({ ...f, display_order: i }));
    });
  }

  function handleAddOption(fieldIndex: number) {
    setFields((prev) =>
      prev.map((f, i) => (i === fieldIndex ? { ...f, options: addOption(f.options ?? []) } : f))
    );
  }

  function handleUpdateOption(fieldIndex: number, optionIndex: number, patch: { value?: string; label?: string }) {
    setFields((prev) =>
      prev.map((f, i) => (i === fieldIndex ? { ...f, options: updateOption(f.options ?? [], optionIndex, patch) } : f))
    );
  }

  function handleRemoveOption(fieldIndex: number, optionIndex: number) {
    setFields((prev) =>
      prev.map((f, i) => (i === fieldIndex ? { ...f, options: removeOption(f.options ?? [], optionIndex) } : f))
    );
  }

  function handleReorderOption(fieldIndex: number, optionIndex: number, direction: -1 | 1) {
    setFields((prev) =>
      prev.map((f, i) =>
        i === fieldIndex ? { ...f, options: reorderOptions(f.options ?? [], optionIndex, direction) } : f
      )
    );
  }

  const fieldErrors = fields.map(validateQualificationField);
  const hasClientErrors = fieldErrors.some((e) => e !== null);

  async function handleSave() {
    if (!receptionistId) return;
    setError(null);
    setSaved(false);
    if (hasClientErrors) {
      setError(fieldErrors.find((e) => e !== null) ?? "Please fix the highlighted fields before saving.");
      return;
    }
    setIsSaving(true);
    try {
      await updateWorkflow(tenantId, receptionistId, {
        qualification_schema: { fields: fields.map((f, i) => ({ ...f, display_order: i })) },
      });
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <p className="text-neutral-500 text-sm">Loading…</p>;
  if (!receptionistId) {
    return <p className="text-sm text-neutral-500">Create a receptionist first to configure qualification fields.</p>;
  }

  return (
    <div className="flex flex-col gap-4 max-w-lg">
      <FieldError message={error} />
      <ul className="flex flex-col gap-3">
        {fields.map((field, index) => {
          const fieldIsSelect = isSelectType(field.type);
          const fieldError = fieldErrors[index];
          return (
            <li key={index} className="rounded border border-black/10 dark:border-white/15 p-3 flex flex-col gap-2">
              <div className="flex gap-2">
                <label className="flex-1 flex flex-col gap-1 text-xs text-neutral-500">
                  Label
                  <input
                    disabled={!canEdit}
                    value={field.label}
                    onChange={(e) => updateField(index, { label: e.target.value })}
                    className={inputClass}
                    aria-label={`Label for field ${field.key}`}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-neutral-500">
                  Type
                  <select
                    disabled={!canEdit}
                    value={field.type}
                    onChange={(e) => handleTypeChange(index, e.target.value)}
                    className={inputClass}
                    aria-label={`Type for field ${field.key}`}
                  >
                    {QUALIFICATION_FIELD_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="flex items-center gap-3 text-sm">
                <label className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    disabled={!canEdit}
                    checked={field.required}
                    onChange={(e) => updateField(index, { required: e.target.checked })}
                  />
                  Required
                </label>
                <span className="text-neutral-500 text-xs">key: {field.key}</span>
                {canEdit && (
                  <div className="ml-auto flex gap-2">
                    <button
                      type="button"
                      onClick={() => moveField(index, -1)}
                      className={secondaryButtonClass}
                      aria-label={`Move field ${field.key} up`}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => moveField(index, 1)}
                      className={secondaryButtonClass}
                      aria-label={`Move field ${field.key} down`}
                    >
                      ↓
                    </button>
                    <button type="button" onClick={() => removeField(index)} className={dangerButtonClass}>
                      Remove
                    </button>
                  </div>
                )}
              </div>

              {fieldIsSelect && (
                <div className="flex flex-col gap-2 border-t border-black/5 dark:border-white/10 pt-2 mt-1">
                  <p className="text-xs font-medium text-neutral-500">Options</p>
                  <ul className="flex flex-col gap-2">
                    {(field.options ?? []).map((option, optionIndex) => (
                      <li key={optionIndex} className="flex items-center gap-2">
                        <input
                          disabled={!canEdit}
                          value={option.label}
                          onChange={(e) => handleUpdateOption(index, optionIndex, { label: e.target.value })}
                          placeholder="Label"
                          className={`${inputClass} flex-1`}
                          aria-label={`Option ${optionIndex + 1} label for field ${field.key}`}
                        />
                        <input
                          disabled={!canEdit}
                          value={option.value}
                          onChange={(e) => handleUpdateOption(index, optionIndex, { value: e.target.value })}
                          placeholder="Stable value"
                          className={`${inputClass} flex-1`}
                          aria-label={`Option ${optionIndex + 1} value for field ${field.key}`}
                        />
                        {canEdit && (
                          <>
                            <button
                              type="button"
                              onClick={() => handleReorderOption(index, optionIndex, -1)}
                              className={secondaryButtonClass}
                              aria-label={`Move option ${optionIndex + 1} up`}
                            >
                              ↑
                            </button>
                            <button
                              type="button"
                              onClick={() => handleReorderOption(index, optionIndex, 1)}
                              className={secondaryButtonClass}
                              aria-label={`Move option ${optionIndex + 1} down`}
                            >
                              ↓
                            </button>
                            <button
                              type="button"
                              onClick={() => handleRemoveOption(index, optionIndex)}
                              className={dangerButtonClass}
                              aria-label={`Delete option ${optionIndex + 1}`}
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </li>
                    ))}
                    {(field.options ?? []).length === 0 && (
                      <li className="text-xs text-neutral-500">No options yet — add at least one.</li>
                    )}
                  </ul>
                  {canEdit && (
                    <button
                      type="button"
                      onClick={() => handleAddOption(index)}
                      className={`${secondaryButtonClass} self-start`}
                    >
                      Add option
                    </button>
                  )}
                </div>
              )}

              {fieldError && (
                <p role="alert" className="text-xs text-red-600 dark:text-red-400">
                  {fieldError}
                </p>
              )}
            </li>
          );
        })}
        {fields.length === 0 && <p className="text-sm text-neutral-500">No qualification fields yet.</p>}
      </ul>

      {canEdit && (
        <div className="flex items-center gap-3">
          <button type="button" onClick={addField} className={secondaryButtonClass}>
            Add field
          </button>
          <button type="button" onClick={handleSave} disabled={isSaving} className={buttonClass}>
            {isSaving ? "Saving…" : "Save"}
          </button>
          <SavedNotice show={saved} />
        </div>
      )}
    </div>
  );
}
