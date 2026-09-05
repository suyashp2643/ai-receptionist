"use client";

import { type ReactNode } from "react";
import { OnboardingProvider } from "@/lib/onboarding-context";
import { OnboardingSteps } from "./OnboardingSteps";

export default function OnboardingLayout({ children }: { children: ReactNode }) {
  return (
    <OnboardingProvider>
      <a href="#onboarding-main-content" className="skip-link">
        Skip to content
      </a>
      <div className="min-h-screen p-8">
        <div className="max-w-3xl mx-auto flex flex-col gap-8">
          <h1 className="text-2xl font-semibold tracking-tight">Set up your receptionist</h1>
          <OnboardingSteps />
          <div id="onboarding-main-content">{children}</div>
        </div>
      </div>
    </OnboardingProvider>
  );
}
