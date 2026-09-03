"use client";

import { useId, useState } from "react";
import { getApiBaseUrl } from "@/lib/config";

type FormState = {
  full_name: string;
  work_email: string;
  company: string;
  website: string;
  country: string;
  industry: string;
  company_size: string;
  estimated_monthly_volume: string;
  primary_use_case: string;
  message: string;
  contact_consent: boolean;
  marketing_consent: boolean;
  hp_field: string; // honeypot — never shown to a real visitor
};

const INITIAL_STATE: FormState = {
  full_name: "",
  work_email: "",
  company: "",
  website: "",
  country: "",
  industry: "",
  company_size: "",
  estimated_monthly_volume: "",
  primary_use_case: "",
  message: "",
  contact_consent: false,
  marketing_consent: false,
  hp_field: "",
};

const COMPANY_SIZES = ["1-10", "11-50", "51-200", "201-500", "500+"];
const VOLUMES = ["Under 50", "50-200", "201-500", "500+"];

type Status = "idle" | "submitting" | "success" | "error";

export function ContactForm() {
  const [form, setForm] = useState<FormState>(INITIAL_STATE);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const formId = useId();

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.contact_consent) {
      setStatus("error");
      setErrorMessage("Please confirm you're okay with us contacting you about this enquiry.");
      return;
    }
    setStatus("submitting");
    setErrorMessage(null);

    try {
      const payload = { ...form, website: form.website.trim() === "" ? undefined : form.website };
      const response = await fetch(`${getApiBaseUrl()}/api/v1/public/leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (response.status === 429) {
        setStatus("error");
        setErrorMessage("Too many submissions from this connection. Please try again in a little while.");
        return;
      }
      if (!response.ok) {
        setStatus("error");
        setErrorMessage("Something went wrong submitting the form. Please check the fields and try again.");
        return;
      }
      setStatus("success");
      setForm(INITIAL_STATE);
    } catch {
      setStatus("error");
      setErrorMessage("Couldn't reach the server. Please check your connection and try again.");
    }
  }

  if (status === "success") {
    return (
      <div role="status" className="rounded-2xl border border-mark-cyan-500/30 bg-mark-cyan-500/[0.06] p-6">
        <h2 className="font-semibold text-white">Thanks — we&apos;ve got it.</h2>
        <p className="mt-2 text-sm text-white/70">
          We&apos;ll follow up at the email you provided. In the meantime, feel free to try one of the interactive
          demos.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field id={`${formId}-name`} label="Full name">
          <input
            id={`${formId}-name`}
            required
            maxLength={200}
            value={form.full_name}
            onChange={(e) => update("full_name", e.target.value)}
            className={inputClass}
            autoComplete="name"
          />
        </Field>
        <Field id={`${formId}-email`} label="Work email">
          <input
            id={`${formId}-email`}
            type="email"
            required
            maxLength={320}
            value={form.work_email}
            onChange={(e) => update("work_email", e.target.value)}
            className={inputClass}
            autoComplete="email"
          />
        </Field>
        <Field id={`${formId}-company`} label="Company">
          <input
            id={`${formId}-company`}
            required
            maxLength={200}
            value={form.company}
            onChange={(e) => update("company", e.target.value)}
            className={inputClass}
            autoComplete="organization"
          />
        </Field>
        <Field id={`${formId}-website`} label="Website (optional)">
          <input
            id={`${formId}-website`}
            type="url"
            maxLength={500}
            placeholder="https://"
            value={form.website}
            onChange={(e) => update("website", e.target.value)}
            className={inputClass}
            autoComplete="url"
          />
        </Field>
        <Field id={`${formId}-country`} label="Country">
          <input
            id={`${formId}-country`}
            required
            maxLength={100}
            value={form.country}
            onChange={(e) => update("country", e.target.value)}
            className={inputClass}
            autoComplete="country-name"
          />
        </Field>
        <Field id={`${formId}-industry`} label="Industry">
          <input
            id={`${formId}-industry`}
            required
            maxLength={100}
            value={form.industry}
            onChange={(e) => update("industry", e.target.value)}
            className={inputClass}
            placeholder="e.g. Clinic, Hotel, Real estate"
          />
        </Field>
        <Field id={`${formId}-size`} label="Team / company size">
          <select
            id={`${formId}-size`}
            required
            value={form.company_size}
            onChange={(e) => update("company_size", e.target.value)}
            className={inputClass}
          >
            <option value="" disabled>
              Select a range
            </option>
            {COMPANY_SIZES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field id={`${formId}-volume`} label="Estimated monthly enquiries/conversations">
          <select
            id={`${formId}-volume`}
            required
            value={form.estimated_monthly_volume}
            onChange={(e) => update("estimated_monthly_volume", e.target.value)}
            className={inputClass}
          >
            <option value="" disabled>
              Select a range
            </option>
            {VOLUMES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <Field id={`${formId}-usecase`} label="Primary use case">
        <input
          id={`${formId}-usecase`}
          required
          maxLength={1000}
          value={form.primary_use_case}
          onChange={(e) => update("primary_use_case", e.target.value)}
          className={inputClass}
          placeholder="e.g. Qualify inbound leads after hours"
        />
      </Field>

      <Field id={`${formId}-message`} label="Message">
        <textarea
          id={`${formId}-message`}
          required
          maxLength={5000}
          rows={4}
          value={form.message}
          onChange={(e) => update("message", e.target.value)}
          className={inputClass}
        />
      </Field>

      {/* Honeypot — visually hidden and off-tab-order, never seen or filled by a real visitor. */}
      <div aria-hidden="true" style={{ position: "absolute", left: "-9999px", width: 1, height: 1, overflow: "hidden" }}>
        <label htmlFor={`${formId}-hp`}>Leave this field empty</label>
        <input
          id={`${formId}-hp`}
          tabIndex={-1}
          autoComplete="off"
          value={form.hp_field}
          onChange={(e) => update("hp_field", e.target.value)}
        />
      </div>

      <label className="flex items-start gap-2 text-sm text-white/75">
        <input
          type="checkbox"
          required
          checked={form.contact_consent}
          onChange={(e) => update("contact_consent", e.target.checked)}
          className="mt-0.5"
        />
        I agree to be contacted about this enquiry. <span aria-hidden="true">*</span>
      </label>
      <label className="flex items-start gap-2 text-sm text-white/60">
        <input
          type="checkbox"
          checked={form.marketing_consent}
          onChange={(e) => update("marketing_consent", e.target.checked)}
          className="mt-0.5"
        />
        I&apos;d also like to receive occasional product updates (optional).
      </label>

      {status === "error" && errorMessage && (
        <p role="alert" className="text-sm text-red-300">
          {errorMessage}
        </p>
      )}

      <button
        type="submit"
        disabled={status === "submitting"}
        className="inline-flex w-fit items-center justify-center rounded-full bg-gradient-to-r from-mark-violet-500 to-mark-violet-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-mark-violet-600/20 transition hover:from-mark-violet-400 hover:to-mark-violet-500 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-mark-navy-950"
      >
        {status === "submitting" ? "Sending…" : "Send"}
      </button>
    </form>
  );
}

const inputClass =
  "w-full rounded-lg border border-white/15 bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-white/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400";

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-white/80">
        {label}
      </label>
      {children}
    </div>
  );
}
