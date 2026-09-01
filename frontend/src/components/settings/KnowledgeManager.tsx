"use client";

import { useEffect, useState } from "react";
import {
  createKnowledgeDocument,
  createKnowledgeSource,
  deleteKnowledgeDocument,
  KnowledgeDocument,
  KnowledgeSearchResult,
  listKnowledgeDocuments,
  listKnowledgeSources,
  searchKnowledge,
  updateKnowledgeDocument,
} from "@/lib/phase3-api";
import { buttonClass, dangerButtonClass, errorMessage, FieldError, inputClass, secondaryButtonClass } from "./shared";

const DEFAULT_SOURCE_TITLE = "Manual knowledge";

export function KnowledgeManager({ tenantId, canEdit }: { tenantId: string; canEdit: boolean }) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [rawText, setRawText] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  async function refresh() {
    try {
      setDocuments(await listKnowledgeDocuments(tenantId));
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

  async function getOrCreateDefaultSourceId(): Promise<string> {
    const sources = await listKnowledgeSources(tenantId);
    const existing = sources.find((s) => s.type === "manual");
    if (existing) return existing.id;
    const created = await createKnowledgeSource(tenantId, DEFAULT_SOURCE_TITLE);
    return created.id;
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      const sourceId = await getOrCreateDefaultSourceId();
      await createKnowledgeDocument(tenantId, { source_id: sourceId, title, raw_text: rawText });
      setTitle("");
      setRawText("");
      setShowForm(false);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleToggleActive(document: KnowledgeDocument) {
    if (!canEdit) return;
    try {
      await updateKnowledgeDocument(tenantId, document.id, {
        status: document.status === "active" ? "inactive" : "active",
      });
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDelete(documentId: string) {
    if (!canEdit) return;
    try {
      await deleteKnowledgeDocument(tenantId, documentId);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setIsSearching(true);
    setError(null);
    try {
      const result = await searchKnowledge(tenantId, searchQuery);
      setSearchResults(result.results);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSearching(false);
    }
  }

  if (isLoading) return <p className="text-neutral-500 text-sm">Loading…</p>;

  return (
    <div className="flex flex-col gap-6 max-w-lg">
      <FieldError message={error} />

      <div>
        <p className="text-sm font-medium mb-2">Documents</p>
        <ul className="flex flex-col gap-2">
          {documents.map((doc) => (
            <li key={doc.id} className="rounded border border-black/10 dark:border-white/15 p-3 text-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className={`font-medium ${doc.status !== "active" ? "line-through text-neutral-400" : ""}`}>
                    {doc.title}
                  </p>
                  <p className="text-neutral-500 mt-1 line-clamp-2">{doc.raw_text}</p>
                </div>
                {canEdit && (
                  <div className="flex flex-col gap-1 shrink-0">
                    <button type="button" onClick={() => handleToggleActive(doc)} className={secondaryButtonClass}>
                      {doc.status === "active" ? "Deactivate" : "Activate"}
                    </button>
                    <button type="button" onClick={() => handleDelete(doc.id)} className={dangerButtonClass}>
                      Delete
                    </button>
                  </div>
                )}
              </div>
            </li>
          ))}
          {documents.length === 0 && <p className="text-sm text-neutral-500">No knowledge documents yet.</p>}
        </ul>

        {canEdit && !showForm && (
          <button type="button" onClick={() => setShowForm(true)} className={`${secondaryButtonClass} mt-3`}>
            Add text document
          </button>
        )}

        {canEdit && showForm && (
          <form
            onSubmit={handleCreate}
            className="flex flex-col gap-3 rounded border border-black/10 dark:border-white/15 p-4 mt-3"
          >
            <label className="flex flex-col gap-1 text-sm">
              Title
              <input required value={title} onChange={(e) => setTitle(e.target.value)} className={inputClass} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Text
              <textarea
                required
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                className={inputClass}
                rows={6}
              />
            </label>
            <div className="flex gap-3">
              <button type="submit" disabled={isSaving} className={buttonClass}>
                {isSaving ? "Saving…" : "Add document"}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className={secondaryButtonClass}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>

      <div>
        <p className="text-sm font-medium mb-2">Test search</p>
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search your knowledge…"
            className={`${inputClass} flex-1`}
          />
          <button type="submit" disabled={isSearching || !searchQuery} className={secondaryButtonClass}>
            {isSearching ? "Searching…" : "Search"}
          </button>
        </form>
        {searchResults && (
          <ul className="flex flex-col gap-2 mt-3">
            {searchResults.map((r) => (
              <li key={r.chunk_id} className="rounded border border-black/10 dark:border-white/15 p-3 text-sm">
                <p className="font-medium">{r.document_title}</p>
                <p className="text-neutral-500 mt-1">{r.content}</p>
              </li>
            ))}
            {searchResults.length === 0 && <p className="text-sm text-neutral-500">No matches.</p>}
          </ul>
        )}
      </div>
    </div>
  );
}
