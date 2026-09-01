"use client";

import { useEffect, useState } from "react";
import { getOnboardingState, updateBusinessProfile } from "@/lib/phase3-api";
import { useTimezoneOptions } from "@/lib/timezones";
import { buttonClass, errorMessage, FieldError, inputClass, SavedNotice } from "./shared";

export function BusinessProfileForm({ tenantId, canEdit }: { tenantId: string; canEdit: boolean }) {
  const [businessName, setBusinessName] = useState("");
  const [shortDescription, setShortDescription] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [publicEmail, setPublicEmail] = useState("");
  const [publicPhone, setPublicPhone] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { timezones } = useTimezoneOptions();

  useEffect(() => {
    (async () => {
      try {
        const state = await getOnboardingState(tenantId);
        const profile = state.business_profile;
        if (profile) {
          setBusinessName(profile.business_name ?? "");
          setShortDescription(profile.short_description ?? "");
          setWebsiteUrl(profile.website_url ?? "");
          setPublicEmail(profile.public_email ?? "");
          setPublicPhone(profile.public_phone ?? "");
          setTimezone(profile.timezone);
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
    try {
      await updateBusinessProfile(tenantId, {
        business_name: businessName,
        short_description: shortDescription || null,
        website_url: websiteUrl || null,
        public_email: publicEmail || null,
        public_phone: publicPhone || null,
        timezone,
      });
      setSaved(true);
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
        Business name
        <input
          required
          disabled={!canEdit}
          value={businessName}
          onChange={(e) => setBusinessName(e.target.value)}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Short description
        <textarea
          disabled={!canEdit}
          value={shortDescription}
          onChange={(e) => setShortDescription(e.target.value)}
          className={inputClass}
          rows={3}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Website URL
        <input
          disabled={!canEdit}
          value={websiteUrl}
          onChange={(e) => setWebsiteUrl(e.target.value)}
          placeholder="https://example.com"
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Public email
        <input
          type="email"
          disabled={!canEdit}
          value={publicEmail}
          onChange={(e) => setPublicEmail(e.target.value)}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Public phone
        <input
          disabled={!canEdit}
          value={publicPhone}
          onChange={(e) => setPublicPhone(e.target.value)}
          placeholder="+14155551234"
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Time zone
        <select
          disabled={!canEdit}
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          className={inputClass}
        >
          {timezones.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </label>
      {canEdit && (
        <div className="flex items-center gap-3">
          <button type="submit" disabled={isSaving} className={buttonClass}>
            {isSaving ? "Saving…" : "Save"}
          </button>
          <SavedNotice show={saved} />
        </div>
      )}
    </form>
  );
}
