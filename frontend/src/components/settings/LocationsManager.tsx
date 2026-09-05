"use client";

import { useEffect, useState } from "react";
import {
  BusinessLocation,
  createLocation,
  DayWorkingHours,
  deleteLocation,
  listLocations,
  updateLocation,
} from "@/lib/phase3-api";
import { DAY_NAMES } from "@/lib/constants";
import { buttonClass, dangerButtonClass, errorMessage, FieldError, inputClass, secondaryButtonClass } from "./shared";

function defaultWorkingHours(): DayWorkingHours[] {
  return Array.from({ length: 7 }, (_, day) => ({
    day_of_week: day,
    closed: day >= 5,
    intervals: day >= 5 ? [] : [{ start: "09:00", end: "17:00" }],
  }));
}

export function LocationsManager({ tenantId, canEdit }: { tenantId: string; canEdit: boolean }) {
  const [locations, setLocations] = useState<BusinessLocation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [days, setDays] = useState<DayWorkingHours[]>(defaultWorkingHours());
  const [isSaving, setIsSaving] = useState(false);

  async function refresh() {
    try {
      setLocations(await listLocations(tenantId));
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

  function updateDay(index: number, patch: Partial<DayWorkingHours>) {
    setDays((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      await createLocation(tenantId, {
        name,
        city: city || null,
        country: country || null,
        is_primary: locations.length === 0,
        working_hours: {
          days: days.map((d) => (d.closed ? { day_of_week: d.day_of_week, closed: true, intervals: [] } : d)),
        },
      });
      setName("");
      setCity("");
      setCountry("");
      setDays(defaultWorkingHours());
      setShowForm(false);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSetPrimary(locationId: string) {
    if (!canEdit) return;
    try {
      await updateLocation(tenantId, locationId, { is_primary: true });
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDelete(locationId: string) {
    if (!canEdit) return;
    try {
      await deleteLocation(tenantId, locationId);
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
        {locations.map((location) => (
          <li
            key={location.id}
            className="flex items-center justify-between rounded border border-black/10 dark:border-white/15 p-3 text-sm"
          >
            <div>
              <p className="font-medium">
                {location.name} {location.is_primary && <span className="text-xs text-neutral-500">(primary)</span>}
              </p>
              <p className="text-neutral-500">
                {[location.city, location.country].filter(Boolean).join(", ") || "No address set"}
              </p>
            </div>
            {canEdit && (
              <div className="flex gap-2">
                {!location.is_primary && (
                  <button type="button" onClick={() => handleSetPrimary(location.id)} className={secondaryButtonClass}>
                    Make primary
                  </button>
                )}
                <button type="button" onClick={() => handleDelete(location.id)} className={dangerButtonClass}>
                  Delete
                </button>
              </div>
            )}
          </li>
        ))}
        {locations.length === 0 && <p className="text-sm text-neutral-500">No locations yet.</p>}
      </ul>

      {canEdit && !showForm && (
        <button type="button" onClick={() => setShowForm(true)} className={secondaryButtonClass}>
          Add location
        </button>
      )}

      {canEdit && showForm && (
        <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded border border-black/10 dark:border-white/15 p-4">
          <label className="flex flex-col gap-1 text-sm">
            Name
            <input required value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            City
            <input value={city} onChange={(e) => setCity(e.target.value)} className={inputClass} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Country
            <input value={country} onChange={(e) => setCountry(e.target.value)} className={inputClass} />
          </label>

          <p className="text-sm font-medium mt-2">Working hours</p>
          {days.map((day, index) => (
            <div key={day.day_of_week} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="w-24">{DAY_NAMES[day.day_of_week]}</span>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={!day.closed}
                  onChange={(e) =>
                    updateDay(index, {
                      closed: !e.target.checked,
                      intervals: e.target.checked ? [{ start: "09:00", end: "17:00" }] : [],
                    })
                  }
                />
                Open
              </label>
              {!day.closed && (
                <>
                  <input
                    type="time"
                    value={day.intervals[0]?.start ?? "09:00"}
                    onChange={(e) =>
                      updateDay(index, {
                        intervals: [{ start: e.target.value, end: day.intervals[0]?.end ?? "17:00" }],
                      })
                    }
                    className={inputClass}
                  />
                  <span>to</span>
                  <input
                    type="time"
                    value={day.intervals[0]?.end ?? "17:00"}
                    onChange={(e) =>
                      updateDay(index, {
                        intervals: [{ start: day.intervals[0]?.start ?? "09:00", end: e.target.value }],
                      })
                    }
                    className={inputClass}
                  />
                </>
              )}
            </div>
          ))}

          <div className="flex gap-3 mt-2">
            <button type="submit" disabled={isSaving} className={buttonClass}>
              {isSaving ? "Saving…" : "Add location"}
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
