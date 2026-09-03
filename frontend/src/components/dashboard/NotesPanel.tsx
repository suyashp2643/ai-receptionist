"use client";

import { useEffect, useState } from "react";
import { createNote, deleteNote, listNotes, type Note, type NoteEntityType } from "@/lib/dashboard-api";

/** Internal notes on one record. Never shown to the public widget and
 * never fed to the AI — clearly separated from customer-facing content. */
export function NotesPanel({
  tenantId,
  entityType,
  entityId,
  currentUserId,
}: {
  tenantId: string;
  entityType: NoteEntityType;
  entityId: string;
  currentUserId: string;
}) {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function load() {
    listNotes(tenantId, entityType, entityId)
      .then(setNotes)
      .catch(() => setError("Could not load internal notes."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, entityType, entityId]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await createNote(tenantId, entityType, entityId, draft.trim());
      setDraft("");
      load();
    } catch {
      setError("Could not save this note.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(noteId: string) {
    try {
      await deleteNote(tenantId, noteId);
      load();
    } catch {
      setError("Could not delete this note.");
    }
  }

  return (
    <section className="rounded-lg border border-black/10 dark:border-white/10 p-4 flex flex-col gap-3" aria-label="Internal notes">
      <div>
        <h2 className="font-medium">Internal notes</h2>
        <p className="text-xs text-neutral-500">Staff-only. Never visible to the visitor, never sent to the AI.</p>
      </div>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {notes === null ? (
        <p className="text-sm text-neutral-500">Loading notes…</p>
      ) : notes.length === 0 ? (
        <p className="text-sm text-neutral-500">No internal notes yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {notes.map((note) => (
            <li key={note.id} className="rounded border border-black/10 dark:border-white/10 p-2 text-sm flex justify-between gap-2">
              <div>
                <p className="whitespace-pre-wrap">{note.body}</p>
                <p className="text-xs text-neutral-500 mt-1">{new Date(note.created_at).toLocaleString()}</p>
              </div>
              {note.author_user_id === currentUserId && (
                <button
                  type="button"
                  onClick={() => handleDelete(note.id)}
                  className="text-xs text-red-600 dark:text-red-400 shrink-0 self-start"
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={handleAdd} className="flex flex-col gap-2">
        <label htmlFor="note-draft" className="sr-only">
          Add an internal note
        </label>
        <textarea
          id="note-draft"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add an internal note…"
          rows={2}
          className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={submitting || !draft.trim()}
          className="self-start rounded bg-foreground text-background px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          Add note
        </button>
      </form>
    </section>
  );
}
