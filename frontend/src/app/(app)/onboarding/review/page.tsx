"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useOnboarding } from "@/lib/onboarding-context";
import { completeOnboarding, getRequirementsFromError, type OnboardingRequirement } from "@/lib/phase3-api";
import { errorMessage, FieldError, buttonClass } from "@/components/settings/shared";
import { StepNav } from "../StepNav";

const STEP_LABELS: Record<string, string> = {
  business_profile: "Business details",
  industry_selected: "Industry template",
  receptionist: "Receptionist",
  locations: "Locations",
  services: "Services",
  knowledge: "Knowledge",
  qualification: "Qualification questions",
  actions: "Allowed actions",
};

const STEP_ROUTE: Record<string, string> = {
  business: "/onboarding/business",
  industry: "/onboarding/industry",
  receptionist: "/onboarding/receptionist",
  locations: "/onboarding/locations",
  services: "/onboarding/services",
  knowledge: "/onboarding/knowledge",
  qualification: "/onboarding/qualification",
  actions: "/onboarding/actions",
};

export default function OnboardingReviewPage() {
  const { tenantId, canEdit, state, refresh } = useOnboarding();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  // Only ever populated from a failed completion attempt's response — the
  // steady-state list always comes live from `state` below. Seeding this
  // from `state` at mount would freeze it to whatever the onboarding
  // context happened to hold at that instant, which can predate its own
  // in-flight refresh (e.g. right after fixing a requirement on another
  // page) and never update again for the lifetime of this component.
  const [attemptRequirements, setAttemptRequirements] = useState<OnboardingRequirement[]>([]);
  const [isCompleting, setIsCompleting] = useState(false);

  async function handleComplete() {
    setError(null);
    setAttemptRequirements([]);
    setIsCompleting(true);
    try {
      await completeOnboarding(tenantId);
      await refresh();
      router.push("/dashboard");
    } catch (err) {
      setError(errorMessage(err));
      setAttemptRequirements(getRequirementsFromError(err));
    } finally {
      setIsCompleting(false);
    }
  }

  const displayedRequirements =
    attemptRequirements.length > 0 ? attemptRequirements : (state?.incomplete_requirements ?? []);

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium">Review</h2>
        <p className="text-sm text-neutral-500">Confirm everything looks right, then complete onboarding.</p>
      </div>

      <FieldError message={error} />

      <ul className="flex flex-col gap-1 text-sm max-w-lg">
        {state &&
          Object.entries(state.steps).map(([key, done]) => (
            <li key={key} className="flex items-center justify-between border-b border-black/5 dark:border-white/10 py-1.5">
              <span>{STEP_LABELS[key] ?? key}</span>
              <span className={done ? "text-green-600 dark:text-green-400" : "text-neutral-400"}>
                {done ? "Complete" : "Not set"}
              </span>
            </li>
          ))}
      </ul>

      {displayedRequirements.length > 0 && (
        <div className="rounded border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-4">
          <p className="text-sm font-medium mb-2">Before you can complete onboarding:</p>
          <ul className="flex flex-col gap-1">
            {displayedRequirements.map((requirement) => (
              <li key={requirement.code} className="text-sm flex items-center justify-between gap-3">
                <span>{requirement.message}</span>
                {STEP_ROUTE[requirement.step] && (
                  <Link href={STEP_ROUTE[requirement.step]} className="underline shrink-0">
                    Fix this
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {canEdit && (
        <button
          type="button"
          onClick={handleComplete}
          disabled={isCompleting || !state?.ready_to_complete}
          className={buttonClass}
        >
          {isCompleting ? "Completing…" : "Complete onboarding"}
        </button>
      )}

      <StepNav back="/onboarding/actions" />
    </section>
  );
}
