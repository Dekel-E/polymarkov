"use client";

import { useEffect, useRef, useState } from "react";
import StepsTrace from "@/components/StepsTrace";
import { executeAgent } from "@/lib/api";
import type { ExecuteOut } from "@/lib/types";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<ExecuteOut | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  async function run() {
    if (!prompt.trim() || running) return;
    setRunning(true);
    setResult(null);
    setFetchError(null);
    setElapsed(0);
    const started = Date.now();
    timerRef.current = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    try {
      setResult(await executeAgent(prompt));
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : String(err));
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl space-y-8 px-4 py-10">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Polymarkov</h1>
        <p className="mt-1 text-sm text-slate-400">
          Pre-trade intelligence dossiers for Polymarket — news, sentiment, AI
          council, deterministic verdict, paper trading. Educational tool, not
          financial advice.
        </p>
      </header>

      <section className="space-y-3">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={4}
          placeholder={
            'e.g. "Analyze the Fed September rate cut market" or paste a Polymarket URL'
          }
          className="w-full resize-y rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm text-slate-100 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
        />
        <div className="flex items-center gap-4">
          <button
            onClick={run}
            disabled={running || !prompt.trim()}
            className="rounded-lg bg-sky-600 px-5 py-2 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? "Running…" : "Run Agent"}
          </button>
          {running && (
            <span className="flex items-center gap-2 text-sm text-slate-400">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
              {elapsed}s elapsed
            </span>
          )}
        </div>
      </section>

      {fetchError && (
        <div className="rounded-lg border border-red-800 bg-red-950/50 p-4 text-sm text-red-300">
          Request failed: {fetchError}
        </div>
      )}

      {result?.status === "error" && (
        <div className="rounded-lg border border-red-800 bg-red-950/50 p-4 text-sm text-red-300">
          Agent error: {result.error}
        </div>
      )}

      {result?.response && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-200">Response</h2>
          <div className="whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm leading-relaxed text-slate-200">
            {result.response}
          </div>
        </section>
      )}

      {result && <StepsTrace steps={result.steps} />}
    </main>
  );
}
