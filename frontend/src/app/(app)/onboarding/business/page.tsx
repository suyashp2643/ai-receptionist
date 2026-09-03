"use client";

import { BusinessProfileForm } from "@/components/settings/BusinessProfileForm";
import { useOnboarding } from "@/lib/onboarding-context";
import { StepNav } from "../StepNav";

export default function OnboardingBusinessPage() {
  const { tenantId, canEdit } = useOnboarding();

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium">Business details</h2>
        <p className="text-sm text-neutral-500">Tell us about your business.</p>
      </div>
      <BusinessProfileForm tenantId={tenantId} canEdit={canEdit} />
      <StepNav next="/onboarding/industry" />
    </section>
  );
}
