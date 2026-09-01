"use client";

import { useEffect, useState } from "react";
import { createFaq, deleteFaq, FAQ, listFaqs, updateFaq } from "@/lib/phase3-api";
import { buttonClass, dangerButtonClass, errorMessage, FieldError, inputClass, secondaryButtonClass } from "./shared";

export function FaqsManager({ tenantId, canEdit }: { tenantId: string; canEdit: boolean }) {
  const [faqs, setFaqs] = useState<FAQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [duplicateNotice, setDuplicateNotice] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function refresh() {
    try {
      setFaqs(await listFaqs(tenantId));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDuplicateNotice(null);
    setIsSaving(true);
    try {
      const result = await createFaq(tenantId, { question, answer });
      if (result.possible_duplicate_of) {
        setDuplicateNotice("This looks similar to an existing FAQ — both have been kept, review for duplicates.");
      }
      setQuestion("");
      setAnswer("");
      setShowForm(false);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleToggleActive(faq: FAQ) {
    if (!canEdit) return;
    try {
      await updateFaq(tenantId, faq.id, { is_active: !faq.is_active });
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDelete(faqId: string) {
    if (!canEdit) return;
    try {
      await deleteFaq(tenantId, faqId);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (isLoading) return <p className="text-neutral-500 text-sm">Loading…</p>;

  return (
    <div className="flex flex-col gap-4 max-w-lg">
      <FieldError message={error} />
      {duplicateNotice && <p className="text-sm text-amber-600 dark:text-amber-400">{duplicateNotice}</p>}
      <ul className="flex flex-col gap-2">
        {faqs.map((faq) => (
          <li key={faq.id} className="rounded border border-black/10 dark:border-white/15 p-3 text-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className={`font-medium ${!faq.is_active ? "line-through text-neutral-400" : ""}`}>
                  {faq.question}
                </p>
                <p className="text-neutral-500 mt-1">{faq.answer}</p>
              </div>
              {canEdit && (
                <div className="flex flex-col gap-1 shrink-0">
                  <button type="button" onClick={() => handleToggleActive(faq)} className={secondaryButtonClass}>
                    {faq.is_active ? "Deactivate" : "Activate"}
                  </button>
                  <button type="button" onClick={() => handleDelete(faq.id)} className={dangerButtonClass}>
                    Delete
                  </button>
                </div>
              )}
            </div>
          </li>
        ))}
        {faqs.length === 0 && <p className="text-sm text-neutral-500">No FAQs yet.</p>}
      </ul>

      {canEdit && !showForm && (
        <button type="button" onClick={() => setShowForm(true)} className={secondaryButtonClass}>
          Add FAQ
        </button>
      )}

      {canEdit && showForm && (
        <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded border border-black/10 dark:border-white/15 p-4">
          <label className="flex flex-col gap-1 text-sm">
            Question
            <input required value={question} onChange={(e) => setQuestion(e.target.value)} className={inputClass} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Answer
            <textarea required value={answer} onChange={(e) => setAnswer(e.target.value)} className={inputClass} rows={3} />
          </label>
          <div className="flex gap-3">
            <button type="submit" disabled={isSaving} className={buttonClass}>
              {isSaving ? "Saving…" : "Add FAQ"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className={secondaryButtonClass}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
