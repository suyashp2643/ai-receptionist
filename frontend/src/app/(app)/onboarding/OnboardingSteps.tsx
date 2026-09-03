"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { useOnboarding } from "@/lib/onboarding-context";
import { countCompletedSteps } from "@/lib/onboarding-progress";

const STEPS: { href: string; label: string; doneKey: keyof NonNullable<ReturnType<typeof useOnboarding>["state"]>["steps"] | null }[] = [
  { href: "/onboarding/business", label: "Business", doneKey: "business_profile" },
  { href: "/onboarding/industry", label: "Industry", doneKey: "industry_selected" },
  { href: "/onboarding/receptionist", label: "Receptionist", doneKey: "receptionist" },
  { href: "/onboarding/locations", label: "Locations", doneKey: "locations" },
  { href: "/onboarding/services", label: "Services", doneKey: "services" },
  { href: "/onboarding/knowledge", label: "Knowledge", doneKey: "knowledge" },
  { href: "/onboarding/qualification", label: "Qualification", doneKey: "qualification" },
  { href: "/onboarding/actions", label: "Actions", doneKey: "actions" },
  { href: "/onboarding/review", label: "Review", doneKey: null },
];

export function OnboardingSteps() {
  const { state, refresh } = useOnboarding();
  const pathname = usePathname();

  // Re-fetch progress whenever the user navigates between onboarding steps,
  // so completing a step and clicking "Next" always shows up-to-date
  // checkmarks — without every individual page needing its own refresh logic.
  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const doneCount = state ? countCompletedSteps(state.steps) : 0;
  const totalSteps = STEPS.length - 1; // exclude "review"

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-neutral-500">
        {doneCount} of {totalSteps} steps complete
      </p>
      <nav className="flex flex-wrap gap-2" aria-label="Onboarding steps">
        {STEPS.map((step) => {
          const isCurrent = pathname === step.href;
          const isDone = step.doneKey ? state?.steps[step.doneKey] : false;
          return (
            <Link
              key={step.href}
              href={step.href}
              aria-current={isCurrent ? "step" : undefined}
              className={`rounded px-3 py-1.5 text-sm border ${
                isCurrent
                  ? "border-foreground bg-black/5 dark:bg-white/10"
                  : "border-black/10 dark:border-white/15"
              }`}
            >
              {isDone ? "✓ " : ""}
              {step.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
