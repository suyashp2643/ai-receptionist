import Link from "next/link";
import { ApiHealthStatus } from "@/components/ApiHealthStatus";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-8 p-8">
      <main className="flex flex-col items-center gap-6 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">AI Receptionist</h1>
        <p className="text-neutral-500 max-w-md">
          Multi-tenant AI receptionist platform — Phase 2 foundation. This page confirms the
          frontend can reach the FastAPI backend.
        </p>
        <ApiHealthStatus />
        <div className="flex gap-4">
          <Link href="/register" className="rounded bg-foreground text-background px-4 py-2 text-sm font-medium">
            Create a workspace
          </Link>
          <Link href="/login" className="rounded border border-black/15 dark:border-white/20 px-4 py-2 text-sm">
            Log in
          </Link>
        </div>
      </main>
    </div>
  );
}
