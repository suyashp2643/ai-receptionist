"use client";

import { IndustrySelector } from "@/components/settings/IndustrySelector";
import { useOnboarding } from "@/lib/onboarding-context";
import { StepNav } from "../StepNav";

export default function OnboardingIndustryPage() {
  const { tenantId, canEdit } = useOnboarding();

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium">Choose an industry template</h2>
        <p className="text-sm text-neutral-500">
          This sets sensible defaults for terminology, qualification questions, and safety rules — you can
          customize everything afterward.
        </p>
      </div>
      <IndustrySelector tenantId={tenantId} canEdit={canEdit} />
      <StepNav back="/onboarding/business" next="/onboarding/receptionist" />
    </section>
  );
}
