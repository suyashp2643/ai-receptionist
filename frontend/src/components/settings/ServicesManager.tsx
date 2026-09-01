"use client";

import { useEffect, useState } from "react";
import { createService, deleteService, listServices, Service, updateService } from "@/lib/phase3-api";
import { buttonClass, dangerButtonClass, errorMessage, FieldError, inputClass, secondaryButtonClass } from "./shared";

export function ServicesManager({ tenantId, canEdit }: { tenantId: string; canEdit: boolean }) {
  const [services, setServices] = useState<Service[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [priceNote, setPriceNote] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function refresh() {
    try {
      setServices(await listServices(tenantId));
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
    setIsSaving(true);
    try {
      await createService(tenantId, { name, price_note: priceNote || null });
      setName("");
      setPriceNote("");
      setShowForm(false);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleToggleActive(service: Service) {
    if (!canEdit) return;
    try {
      await updateService(tenantId, service.id, { is_active: !service.is_active });
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDelete(serviceId: string) {
    if (!canEdit) return;
    try {
      await deleteService(tenantId, serviceId);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (isLoading) return <p className="text-neutral-500 text-sm">Loading…</p>;

  return (
    <div className="flex flex-col gap-4 max-w-lg">
      <FieldError message={error} />
      <ul className="flex flex-col gap-2">
        {services.map((service) => (
          <li
            key={service.id}
            className="flex items-center justify-between rounded border border-black/10 dark:border-white/15 p-3 text-sm"
          >
            <div>
              <p className={`font-medium ${!service.is_active ? "line-through text-neutral-400" : ""}`}>
                {service.name}
              </p>
              {service.price_note && <p className="text-neutral-500">{service.price_note}</p>}
            </div>
            {canEdit && (
              <div className="flex gap-2">
                <button type="button" onClick={() => handleToggleActive(service)} className={secondaryButtonClass}>
                  {service.is_active ? "Deactivate" : "Activate"}
                </button>
                <button type="button" onClick={() => handleDelete(service.id)} className={dangerButtonClass}>
                  Delete
                </button>
              </div>
            )}
          </li>
        ))}
        {services.length === 0 && <p className="text-sm text-neutral-500">No services yet.</p>}
      </ul>

      {canEdit && !showForm && (
        <button type="button" onClick={() => setShowForm(true)} className={secondaryButtonClass}>
          Add service
        </button>
      )}

      {canEdit && showForm && (
        <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded border border-black/10 dark:border-white/15 p-4">
          <label className="flex flex-col gap-1 text-sm">
            Name
            <input required value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Price note
            <input
              value={priceNote}
              onChange={(e) => setPriceNote(e.target.value)}
              placeholder="e.g. Starting at $50"
              className={inputClass}
            />
          </label>
          <div className="flex gap-3">
            <button type="submit" disabled={isSaving} className={buttonClass}>
              {isSaving ? "Saving…" : "Add service"}
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
