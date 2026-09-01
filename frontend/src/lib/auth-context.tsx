"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { apiRequest, apiRequestWithCsrf, refreshAccessToken, setAccessToken } from "@/lib/api";

export interface UserPublic {
  id: string;
  normalized_email: string;
  display_name: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface TenantMembershipSummary {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: "owner" | "admin" | "member";
  status: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserPublic;
  memberships: TenantMembershipSummary[];
}

export interface RegisterInput {
  display_name: string;
  email: string;
  password: string;
  workspace_name: string;
  timezone: string;
}

interface AuthState {
  user: UserPublic | null;
  memberships: TenantMembershipSummary[];
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  register(input: RegisterInput): Promise<void>;
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, memberships: [], isLoading: true });

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      const restored = await refreshAccessToken();
      if (!restored) {
        if (!cancelled) setState({ user: null, memberships: [], isLoading: false });
        return;
      }
      try {
        const me = await apiRequest<{ user: UserPublic; memberships: TenantMembershipSummary[] }>(
          "/api/v1/auth/me"
        );
        if (!cancelled) setState({ user: me.user, memberships: me.memberships, isLoading: false });
      } catch {
        if (!cancelled) setState({ user: null, memberships: [], isLoading: false });
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const data = await apiRequest<TokenResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
    });
    setAccessToken(data.access_token);
    setState({ user: data.user, memberships: data.memberships, isLoading: false });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiRequest<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setAccessToken(data.access_token);
    setState({ user: data.user, memberships: data.memberships, isLoading: false });
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiRequestWithCsrf("/api/v1/auth/logout", { method: "POST" });
    } finally {
      setAccessToken(null);
      setState({ user: null, memberships: [], isLoading: false });
    }
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, register, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
