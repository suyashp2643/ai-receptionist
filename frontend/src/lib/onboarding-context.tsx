"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { getOnboardingState, OnboardingState } from "@/lib/phase3-api";
import { computeOnboardingRedirect } from "@/lib/onboarding-redirect";

interface OnboardingContextValue {
  tenantId: string;
  role: "owner" | "admin" | "member";
  canEdit: boolean;
  state: OnboardingState | null;
  refresh: () => Promise<void>;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { user, memberships, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const [state, setState] = useState<OnboardingState | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const membership = memberships[0];

  const refresh = useCallback(async () => {
    if (!membership) return;
    const nextState = await getOnboardingState(membership.tenant_id);
    setState(nextState);
  }, [membership]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      // First pass: decide based on what we already know synchronously
      // (auth state, membership, role) before ever calling the API.
      const earlyRedirect = computeOnboardingRedirect({
        authLoading,
        hasUser: !!user,
        hasMembership: !!membership,
        role: membership?.role ?? null,
        onboardingStatus: null,
      });
      if (authLoading) return;
      if (earlyRedirect) {
        router.replace(earlyRedirect);
        return;
      }

      try {
        const nextState = await getOnboardingState(membership!.tenant_id);
        if (cancelled) return;
        const redirect = computeOnboardingRedirect({
          authLoading: false,
          hasUser: true,
          hasMembership: true,
          role: membership!.role,
          onboardingStatus: nextState.status,
        });
        if (redirect) {
          router.replace(redirect);
          return;
        }
        setState(nextState);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, membership]);

  if (authLoading || isLoading || !membership) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-neutral-500">Loading…</p>
      </div>
    );
  }

  return (
    <OnboardingContext.Provider
      value={{
        tenantId: membership.tenant_id,
        role: membership.role,
        canEdit: membership.role === "owner" || membership.role === "admin",
        state,
        refresh,
      }}
    >
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext);
  if (!ctx) throw new Error("useOnboarding must be used within an OnboardingProvider");
  return ctx;
}
