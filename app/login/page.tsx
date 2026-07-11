"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { authConfigured, useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await signIn(email, password);
      } else {
        await signUp(email, password);
      }
      router.push("/portfolio");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!authConfigured) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-5 text-sm text-amber-300">
          Auth is not configured — set NEXT_PUBLIC_SUPABASE_URL and
          NEXT_PUBLIC_SUPABASE_ANON_KEY in .env, then restart the dev server.
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <div className="rounded-2xl border border-desk-line bg-desk-panel/60 p-6 shadow-xl shadow-black/20">
        <h1 className="text-xl font-bold tracking-tight">
          {mode === "login" ? "Welcome back" : "Create an account"}
        </h1>
        <p className="mt-1 text-sm text-desk-dim">
          {mode === "login"
            ? "Log in to track and direct your own paper trades."
            : "Register to get your own paper-trading book."}
        </p>

        <form onSubmit={submit} className="mt-5 space-y-3">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-xl border border-desk-line bg-desk-deep/80 px-3.5 py-2.5 text-sm text-desk-ink placeholder-desk-faint focus:border-instrument/60 focus:outline-none"
          />
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password (min 6 characters)"
            className="w-full rounded-xl border border-desk-line bg-desk-deep/80 px-3.5 py-2.5 text-sm text-desk-ink placeholder-desk-faint focus:border-instrument/60 focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl bg-instrument px-4 py-2.5 text-sm font-bold text-desk-deep transition hover:bg-instrument-bright disabled:opacity-40"
          >
            {busy ? "Working…" : mode === "login" ? "Log in" : "Register"}
          </button>
        </form>

        {error && (
          <div className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        <button
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
          className="mt-4 text-xs text-desk-dim transition hover:text-desk-soft"
        >
          {mode === "login"
            ? "No account yet? Register instead"
            : "Already registered? Log in instead"}
        </button>
      </div>

      <p className="mt-4 text-center text-[11px] text-desk-faint">
        Login is optional — the agent and all analysis pages work without an account.
      </p>
    </div>
  );
}
