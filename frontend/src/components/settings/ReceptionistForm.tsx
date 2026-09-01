"use client";

import { useEffect, useState } from "react";
import {
  createReceptionist,
  listReceptionists,
  Receptionist,
  updateReceptionist,
} from "@/lib/phase3-api";
import { SUGGESTED_TONES } from "@/lib/constants";
import { buttonClass, errorMessage, FieldError, inputClass, SavedNotice } from "./shared";

export function ReceptionistForm({
  tenantId,
  canEdit,
  onSaved,
}: {
  tenantId: string;
  canEdit: boolean;
  onSaved?: (receptionist: Receptionist) => void;
}) {
  const [receptionist, setReceptionist] = useState<Receptionist | null>(null);
  const [name, setName] = useState("");
  const [welcomeMessage, setWelcomeMessage] = useState("");
  const [tone, setTone] = useState("");
  const [accentColor, setAccentColor] = useState("");
  const [suggestedQuestions, setSuggestedQuestions] = useState("");
  const [status, setStatus] = useState<Receptionist["status"]>("draft");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const list = await listReceptionists(tenantId);
        const existing = list[0] ?? null;
        setReceptionist(existing);
        if (existing) {
          setName(existing.name);
          setWelcomeMessage(existing.welcome_message);
          setTone(existing.tone ?? "");
          setAccentColor(existing.accent_color ?? "");
          setSuggestedQuestions(existing.suggested_questions.join("\n"));
          setStatus(existing.status);
        }
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setIsLoading(false);
      }
    })();
  }, [tenantId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    setIsSaving(true);
    const questions = suggestedQuestions
      .split("\n")
      .map((q) => q.trim())
      .filter(Boolean);
    try {
      const payload = {
        name,
        welcome_message: welcomeMessage,
        tone: tone || null,
        accent_color: accentColor || null,
        suggested_questions: questions,
        ...(receptionist ? { status } : {}),
      };
      const result = receptionist
        ? await updateReceptionist(tenantId, receptionist.id, payload)
        : await createReceptionist(tenantId, payload);
      setReceptionist(result);
      setSaved(true);
      onSaved?.(result);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <p className="text-neutral-500 text-sm">Loading…</p>;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 max-w-lg">
      <FieldError message={error} />
      <label className="flex flex-col gap-1 text-sm">
        Receptionist name
        <input
          required
          disabled={!canEdit}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Welcome message
        <textarea
          disabled={!canEdit}
          value={welcomeMessage}
          onChange={(e) => setWelcomeMessage(e.target.value)}
          className={inputClass}
          rows={3}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Tone
        <select disabled={!canEdit} value={tone} onChange={(e) => setTone(e.target.value)} className={inputClass}>
          <option value="">Not set</option>
          {SUGGESTED_TONES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Accent color
        <input
          disabled={!canEdit}
          value={accentColor}
          onChange={(e) => setAccentColor(e.target.value)}
          placeholder="#1A2B3C"
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Suggested questions (one per line)
        <textarea
          disabled={!canEdit}
          value={suggestedQuestions}
          onChange={(e) => setSuggestedQuestions(e.target.value)}
          className={inputClass}
          rows={4}
        />
      </label>
      {receptionist && (
        <label className="flex flex-col gap-1 text-sm">
          Status
          <select
            disabled={!canEdit}
            value={status}
            onChange={(e) => setStatus(e.target.value as Receptionist["status"])}
            className={inputClass}
          >
            <option value="draft">Draft — not yet live</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
          </select>
          <span className="text-xs text-neutral-500">
            Onboarding requires this to be Active before it can be completed.
          </span>
        </label>
      )}
      {canEdit && (
        <div className="flex items-center gap-3">
          <button type="submit" disabled={isSaving} className={buttonClass}>
            {isSaving ? "Saving…" : receptionist ? "Save" : "Create receptionist"}
          </button>
          <SavedNotice show={saved} />
        </div>
      )}
    </form>
  );
}
