"use client";

import { FaqsManager } from "@/components/settings/FaqsManager";
import { KnowledgeManager } from "@/components/settings/KnowledgeManager";
import { useOnboarding } from "@/lib/onboarding-context";
import { StepNav } from "../StepNav";

export default function OnboardingKnowledgePage() {
  const { tenantId, canEdit } = useOnboarding();

  return (
    <section className="flex flex-col gap-8">
      <div>
        <h2 className="text-lg font-medium">Knowledge</h2>
        <p className="text-sm text-neutral-500">
          Optional — add FAQs and plain-text business knowledge your receptionist can draw on later.
        </p>
      </div>
      <div>
        <h3 className="text-sm font-semibold mb-2">FAQs</h3>
        <FaqsManager tenantId={tenantId} canEdit={canEdit} />
      </div>
      <div>
        <h3 className="text-sm font-semibold mb-2">Text documents</h3>
        <KnowledgeManager tenantId={tenantId} canEdit={canEdit} />
      </div>
      <StepNav back="/onboarding/services" next="/onboarding/qualification" />
    </section>
  );
}
