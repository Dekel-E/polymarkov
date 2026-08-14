"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type ChatTurn, executeAgent } from "./api";
import type { ExecuteOut } from "./types";

export interface RunRecord {
  prompt: string;
  summary: string; // short assistant summary carried as follow-up context
}

function summarize(result: ExecuteOut): string {
  const v = result.ui?.verdict;
  const slug = result.ui?.market?.slug;
  if (v && slug) {
    return `analyzed market ${slug}: verdict ${v.verdict}, fair probability ${(v.fair_probability * 100).toFixed(1)}%`;
  }
  return (result.response ?? "").slice(0, 240);
}

export function useAgentRun() {
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<ExecuteOut | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [pastRuns, setPastRuns] = useState<RunRecord[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runningRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      abortRef.current?.abort();
    };
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    runningRef.current = false;
    setRunning(false);
    setElapsed(0);
    setResult(null);
    setFetchError(null);
    setPastRuns([]);
  }, []);

  async function run(prompt: string) {
    const text = prompt.trim();
    if (!text || runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    setResult(null);
    setFetchError(null);
    setElapsed(0);
    const controller = new AbortController();
    abortRef.current = controller;
    const started = Date.now();
    timerRef.current = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    // prior turns let the planner resolve follow-ups
    const history: ChatTurn[] = pastRuns.flatMap((r) => [
      { role: "user" as const, content: r.prompt },
      { role: "assistant" as const, content: r.summary },
    ]);
    try {
      const res = await executeAgent(text, history.slice(-8), controller.signal);
      if (abortRef.current !== controller) return;
      setResult(res);
      if (res.status === "ok") {
        setPastRuns((prev) => [...prev.slice(-5), { prompt: text, summary: summarize(res) }]);
      }
    } catch (err) {
      if (abortRef.current === controller && !(err instanceof DOMException && err.name === "AbortError")) {
        setFetchError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (abortRef.current !== controller) return;
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
      abortRef.current = null;
      runningRef.current = false;
      setRunning(false);
    }
  }

  return { running, elapsed, result, fetchError, run, reset, pastRuns };
}
